"""
Run the full pipeline, configured by a config file, but without calling a series of other scripts.
"""

# pythonpath modification to make hytra available
# for import without requiring it to be installed
import os
import sys
sys.path.insert(0, os.path.abspath('..'))

import logging
import commentjson as json
import dpct
from subprocess import check_call
import configargparse as argparse
import hytra.core.ilastik_project_options
from hytra.core.jsongraph import JsonTrackingGraph
from hytra.core.ilastikhypothesesgraph import IlastikHypothesesGraph
from hytra.core.fieldofview import FieldOfView
from hytra.core.mergerresolver import MergerResolver

def convertToDict(unknown):
    keys = [u.replace('--', '') for u in unknown[0:None:2]]
    values = unknown[1:None:2]
    return dict(zip(keys, values))

def constructFov(shape, t0, t1, scale=[1, 1, 1]):
    [xshape, yshape, zshape] = shape
    [xscale, yscale, zscale] = scale

    fov = FieldOfView(t0, 0, 0, 0, t1, xscale * (xshape - 1), yscale * (yshape - 1),
                      zscale * (zshape - 1))
    return fov

def run_pipeline(options, unknown):
    """
    Run the complete tracking pipeline by invoking the scripts as subprocesses.
    Using the `do-SOMETHING` switches one can configure which parts of the pipeline are run.

    **Params:**

    * `options`: the options of the tracking script as returned from argparse
    * `unknown`: unknown parameters read from the config file, needed in case merger resolving is supposed to be run.

    """

    params = convertToDict(unknown)

    # if options.do_ctc_groundtruth_conversion:
    #     logging.info("Convert CTC groundtruth to our format...")
    #     check_call(["python", os.path.abspath("ctc/ctc_gt_to_hdf5.py"), "--config", options.config_file])

    # if options.do_ctc_raw_data_conversion:
    #     logging.info("Convert CTC raw data to HDF5...")
    #     check_call(["python", os.path.abspath("ctc/stack_to_h5.py"), "--config", options.config_file])

    # if options.do_ctc_segmentation_conversion:
    #     logging.info("Convert CTC segmentation to HDF5...")
    #     check_call(["python", os.path.abspath("ctc/segmentation_to_hdf5.py"), "--config", options.config_file])

    # if options.do_train_transition_classifier:
    #     logging.info("Train transition classifier...")
    #     check_call(["python", os.path.abspath("train_transition_classifier.py"), "--config", options.config_file])

    if options.do_extract_weights:
        logging.info("Extracting weights from ilastik project...")
        weights = hytra.core.ilastik_project_options.extractWeightDictFromIlastikProject(params['ilastik-tracking-project'])
    else:
        with open(options.weight_filename, 'r') as f:
            weights = json.load(f)

    if options.do_create_graph:
        logging.info("Create hypotheses graph...")

        import hytra.core.traxelstore as traxelstore
        from hytra.core.ilastik_project_options import IlastikProjectOptions
        ilpOptions = IlastikProjectOptions()
        ilpOptions.labelImagePath = params['label-image-path']
        ilpOptions.labelImageFilename = params['label-image-file']
        ilpOptions.rawImagePath = params['raw-data-path']
        ilpOptions.rawImageFilename = params['raw-data-file']
        try:
            ilpOptions.rawImageAxes = params['raw-data-axes']
        except:
            ilpOptions.rawImageAxes = 'txyzc'

        ilpOptions.sizeFilter = [int(params['min-size']), 100000]

        if 'object-count-classifier-file' in params:
            ilpOptions.objectCountClassifierFilename = params['object-count-classifier-file']
        else:
            ilpOptions.objectCountClassifierFilename = params['ilastik-tracking-project']

        if 'division-classifier-file' in params:
            ilpOptions.divisionClassifierFilename = params['division-classifier-file']
        else:
            ilpOptions.divisionClassifierFilename = None # params['ilastik-tracking-project']

        traxelstore = traxelstore.Traxelstore(ilpOptions, 
                                              pluginPaths=['../hytra/plugins'],
                                              useMultiprocessing=False)

        # if time_range is not None:
        #     traxelstore.timeRange = time_range

        traxelstore.fillTraxelStore(usePgmlink=False)
        fieldOfView = constructFov(traxelstore.shape,
                                   traxelstore.timeRange[0],
                                   traxelstore.timeRange[1],
                                   [traxelstore.x_scale,
                                   traxelstore.y_scale,
                                   traxelstore.z_scale])

        hypotheses_graph = IlastikHypothesesGraph(
            traxelstore=traxelstore,
            maxNumObjects=int(params['max-number-objects']),
            numNearestNeighbors=int(params['max-nearest-neighbors']),
            fieldOfView=fieldOfView,
            withDivisions=False,#'without-divisions' not in params,
            withTracklets=False,
            divisionThreshold=0.1
        )

        trackingGraph = hypotheses_graph.toTrackingGraph()
    else:
        trackingGraph = JsonTrackingGraph(model_filename=options.model_filename)

    if options.do_convexify:
        logging.info("Convexifying graph energies...")
        trackingGraph.convexifyCosts()

    # get model out of trackingGraph
    model = trackingGraph.model

    if options.do_tracking:
        logging.info("Run tracking...")
        result = dpct.trackFlowBased(model, weights)
        hytra.core.jsongraph.writeToFormattedJSON(options.result_filename, result)

    extra_params = []
    if options.do_merger_resolving:
        logging.info("Run merger resolving")
        trackingGraph = JsonTrackingGraph(model=model, result=result)
        merger_resolver = MergerResolver(trackingGraph)
        ilpOptions.labelImagePath = params['label-image-path']
        ilpOptions.labelImageFilename = params['label-image-file']
        ilpOptions.rawImagePath = params['raw-data-path']
        ilpOptions.rawImageFilename = params['raw-data-file']
        try:
            ilpOptions.rawImageAxes = params['raw-data-axes']
        except:
            ilpOptions.rawImageAxes = 'txyzc'
        merger_resolver.run(
            ilpOptions.labelImageFilename,
            ilpOptions.labelImagePath,
            ilpOptions.rawImageFilename,
            ilpOptions.rawImagePath,
            ilpOptions.rawImageAxes,
            params['out-label-image-file'],
            ['../hytra/plugins'],
            None,
            None,
            True)

    #     for p in ["--out-graph-json-file", "--out-label-image-file", "--out-result-json-file"]:
    #         index = unknown.index(p)
    #         extra_params.append(p.replace('--out-', '--'))
    #         extra_params.append(unknown[index + 1])

    # if options.export_format is not None:
    #     logging.info("Convert result to {}...".format(options.export_format))
    #     if options.export_format in ['ilastikH5', 'ctc']:
    #         check_call(["python", os.path.abspath("json_result_to_events.py"), "--config", options.config_file] + extra_params)
    #         if options.export_format == 'ctc':
    #             check_call(["python", os.path.abspath("ctc/hdf5_to_ctc.py"), "--config", options.config_file] + extra_params)
    #     elif options.export_format == 'labelimage':
    #         check_call(["python", os.path.abspath("json_result_to_labelimage.py"), "--config", options.config_file] + extra_params)
    #     elif options.export_format is not None:
    #         logging.error("Unknown export format chosen!")
    #         raise ValueError("Unknown export format chosen!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Cell Tracking Pipeline',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-c', '--config', is_config_file=True, help='config file path', dest='config_file', required=True)

    parser.add_argument("--do-ctc-groundtruth-conversion", dest='do_ctc_groundtruth_conversion', action='store_true', default=False)
    parser.add_argument("--do-ctc-raw-data-conversion", dest='do_ctc_raw_data_conversion', action='store_true', default=False)
    parser.add_argument("--do-ctc-segmentation-conversion", dest='do_ctc_segmentation_conversion', action='store_true', default=False)
    parser.add_argument("--do-train-transition-classifier", dest='do_train_transition_classifier', action='store_true', default=False)
    parser.add_argument("--do-extract-weights", dest='do_extract_weights', action='store_true', default=False)
    parser.add_argument("--do-create-graph", dest='do_create_graph', action='store_true', default=False)
    parser.add_argument("--do-convexify", dest='do_convexify', action='store_true', default=False)
    parser.add_argument("--do-tracking", dest='do_tracking', action='store_true', default=False)
    parser.add_argument("--do-merger-resolving", dest='do_merger_resolving', action='store_true', default=False)
    parser.add_argument("--export-format", dest='export_format', type=str, default=None,
                        help='Export format may be one of: "ilastikH5", "ctc", "labelimage", or None')
    parser.add_argument("--tracking-executable", dest='tracking_executable', required=True,
                        type=str, help='executable that can run tracking based on JSON specified models')
    parser.add_argument('--graph-json-file', required=True, type=str, dest='model_filename',
                        help='Filename of the json graph description')
    parser.add_argument('--result-json-file', required=True, type=str, dest='result_filename',
                        help='Filename of the json file containing results')
    parser.add_argument('--weight-json-file', required=True, type=str, dest='weight_filename',
                        help='Filename of the weights stored in json')
    parser.add_argument("--verbose", dest='verbose', action='store_true', default=False)

    # parse command line
    options, unknown = parser.parse_known_args()

    if options.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    logging.debug("Ignoring unknown parameters: {}".format(unknown))

    run_pipeline(options, unknown)
