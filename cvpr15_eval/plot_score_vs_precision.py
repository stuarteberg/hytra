#!/usr/bin/env python

import os.path
import sys
sys.path.append('.')
sys.path.append(os.path.dirname(os.path.abspath(__file__)) + '/../toolbox/.')

import numpy as np
import matplotlib.pyplot as plt
import argparse
import math
import structsvm
import trackingfeatures


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Scatter-Plot the precision of a lineage vs the reranker score')

    # file paths
    parser.add_argument('--lineage', type=str, required=True, dest='lineage_filename',
                        help='Lineage tree dump')
    parser.add_argument('--precisions', type=str, required=True, dest='precisions_filename',
                        help='file containing the precision against the ground truth of each lineage tree')
    parser.add_argument('--reranker-weights', type=str, dest='reranker_weights',
                        help='file containing the learned reranker weights')
    parser.add_argument('-o', required=True, type=str, dest='out_file',
                        help='Name of the file the plot is saved to')

    options = parser.parse_args()

    # load
    precisions = np.loadtxt(options.precisions_filename)
    tracks, divisions, lineage_trees = trackingfeatures.load_lineage_dump(options.lineage_filename)
    print("Found {} tracks, {} divisions and {} lineage trees".format(len(tracks),
                                                                      len(divisions),
                                                                      len(lineage_trees)))
    weights = np.loadtxt(options.reranker_weights)
    means = np.loadtxt(os.path.splitext(options.reranker_weights)[0] + '_means.txt')
    variances = np.loadtxt(os.path.splitext(options.reranker_weights)[0] + '_variances.txt')

    # compute scores
    scores = []
    num_divs = []
    num_tracks = []
    lengths = []
    for lt in lineage_trees:
        feat_vec = np.expand_dims(lt.get_expanded_feature_vector([-1, 2]), axis=1)
        structsvm.utils.apply_feature_normalization(feat_vec, means, variances)
        score = np.dot(weights, feat_vec[:, 0])
        scores.append(score)
        num_divs.append(len(lt.divisions))
        num_tracks.append(len(lt.tracks))
        lengths.append(sum([t.length for t in lt.tracks]))

    # scatter plot
    plt.figure()
    plt.hold(True)
    plt.scatter(precisions, scores)
    plt.xlabel("Precision")
    plt.ylabel("Score")
    plt.savefig(options.out_file)

    # sort according to precision and plot again
    log_scores = map(math.log, scores)
    prec_score_pairs = zip(list(precisions), scores, num_divs, num_tracks, lengths)
    prec_score_pairs.sort(key=lambda x: x[1])

    plt.figure()
    plt.hold(True)
    plt.plot(zip(*prec_score_pairs)[1], zip(*prec_score_pairs)[0])
    plt.ylabel("Precision")
    plt.xlabel("Score")
    filename, extension = os.path.splitext(options.out_file)
    plt.savefig(filename + "_sorted" + extension)

    plt.figure()
    plt.hold(True)
    plt.scatter(zip(*prec_score_pairs)[2], zip(*prec_score_pairs)[1], c='b', label='Num divisions')
    plt.scatter(zip(*prec_score_pairs)[3], zip(*prec_score_pairs)[1], c='r', label='Num tracks')
    # plt.plot(zip(*prec_score_pairs)[4], zip(*prec_score_pairs)[1], c='g', label='overall lengths')
    plt.xlabel("Length")
    plt.ylabel("Score")
    plt.legend()
    filename, extension = os.path.splitext(options.out_file)
    plt.savefig(filename + "_length_score" + extension)

    plt.figure()
    plt.hold(True)
    plt.scatter(zip(*prec_score_pairs)[2], zip(*prec_score_pairs)[0], c='b', label='Num divisions')
    plt.scatter(zip(*prec_score_pairs)[3], zip(*prec_score_pairs)[0], c='r', label='Num tracks')
    # plt.scatter(zip(*prec_score_pairs)[4], zip(*prec_score_pairs)[0], c='g', label='overall lengths')
    plt.xlabel("Length")
    plt.ylabel("Precision")
    plt.legend()
    filename, extension = os.path.splitext(options.out_file)
    plt.savefig(filename + "_length_precision" + extension)
    