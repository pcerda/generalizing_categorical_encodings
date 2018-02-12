
import time
import sys
import numpy as np
import pandas as pd
import glob
import os
from sklearn import svm
from sklearn import linear_model
from sklearn import preprocessing
from sklearn import metrics
from sklearn import neural_network
from sklearn import ensemble
from sklearn import neighbors
from sklearn import cluster
from sklearn import kernel_approximation
from sklearn import decomposition
from sklearn import random_projection
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import LabelEncoder
import datetime
from joblib import Parallel, delayed, Memory
import string
from itertools import accumulate
from operator import itemgetter
from scipy import interpolate
from scipy import stats
from scipy import sparse
import matplotlib.pyplot as plt
import seaborn as sns

from ngrams_vectorizer import *
from count_3_grams import *
import ngram
from pyjarowinkler import distance as jwdistance
import jellyfish
import Levenshtein as lev
import distance as dist
import json
import itertools
import pickle

import random
import collections
from functools import lru_cache
import category_encoders as ce

from constants import epochs, val_split, rescaling_factor
memory = Memory(cachedir='./joblib')
from model import NNetEstimator, NNetBinaryClassifier


def append_input_shape_to_configs(shapes, configs, rescale_layer_number=True):
    new_configs = []
    for c, s in zip(configs, shapes):
        c.shape = s
        if rescale_layer_number:
            c.rescale_layer_number(factor=rescaling_factor)
        new_configs.append(c)
    return new_configs


def string_normalize(s):
    res = str(s).lower()
    res = ' ' + res + ' '
    # res = ''.join(str(c) for c in res if ((c.isalnum()) or (c == ' ')))
    # if res is '':
    #     res = ' '
    return res


def preprocess_data(df, cols):
    for col in cols:
        print('Preprocessing column: %s' % col)
        df[col] = [string_normalize(str(r)) for r in df[col]]
    return df


def compare_strings(a, A):
    xout = np.where(A == a, 1, 0).reshape(1, -1)
    return xout


def process_column(X1, X2, y_train, clf_type, method, xcols, encoder, n_jobs,
                   dimension_reduction):
    """
    single-column processing function.
    :param X1: test or training input column
    :param X2: test or training input column
    :param y_train: output
    :param clf_type:
    :param method: method, among num, ohe, se (see transformX for more details)
    :param xcols: str
    :param encoder: str among different distances or encoding methods used if
                    method is se
    :param n_jobs:
    :param dimension_reduction:
    :return:
    """
    if method == 'num':
        X1 = X1.astype('float32')
        x_out = X1.reshape(-1, 1)
        col_value_list = [xcols]
    else:
        X1 = X1.astype(str)
        X2 = X2.astype(str)
        if method == 'array':
            print('array method!')
            x_out = arrayvalues2mat(X1)
            col_value_list = [(xcols, str(i))
                              for i in range(x_out.shape[1])]
        else:
            unqX2 = np.unique(X2)
            if method == 'se':
                # alert: verify that test and train have the exact same
                # dimension reduction, which is not the case right now
                x_out, col_value_list = dimension_reduction_cat_var(
                    dimension_reduction[0], dimension_reduction[1],
                    X1, X2, y_train, clf_type, xcols, encoder, n_jobs)
            if method == 'ohe':
                x_out = one_hot_encoding(X1, unqX2, n_jobs)
                col_value_list = [xcols + '_' + s for s in unqX2]
            if method == 'ohe-1':
                x_out = one_hot_encoding(X1, unqX2, n_jobs)
                x_out = x_out[:, :-1]
                col_value_list = [xcols + '_' + s for s in unqX2]
                col_value_list = col_value_list[:-1]
            if method == 'del':
                col_value_list = []
                x_out = np.array([])
    return (x_out, col_value_list)


def dimension_reduction_cat_var(method, d, X1, X2, y_train, clf_type,
                                col_name, encoder, n_jobs):
    """

    :param method: dimension reduction  method (RandomProjection, Kmeans...)
    :param d: output dimension after the dimension reduction is applied
    :param X1:
    :param X2:
    :param y_train:
    :param clf_type:
    :param col_name:
    :param distance:
    :param n_jobs:
    :return:
    """
    unqX2 = np.unique(X2)
    if method == '-':
        x_out = categorical_encoding(X1, X2, y_train, encoder, clf_type,
                                     n_jobs)
        col_value_list = [(col_name, s)
                          for s in range(x_out.shape[-1])]

    if method == 'RandomProjectionsGaussian':
        unqX1 = np.unique(X1)
        unqX2 = np.unique(X2)
        SE = categorical_encoding(unqX2, unqX2, y_train, encoder, clf_type,
                                  n_jobs)
        rand_proj = random_projection.GaussianRandomProjection(
                    n_components=d,
                    random_state=87)
        SE = categorical_encoding(unqX1, unqX2, y_train, encoder, clf_type,
                                  n_jobs)
        SE = rand_proj.fit_transform(SE)
        x_out = np.zeros((len(X1), d))
        dict1 = {x: SE[i] for i, x in enumerate(unqX1)}
        for i, x in enumerate(X1):
            x_out[i] = dict1[x]
        col_value_list = [(col_name, j) for j in range(d)]
    if method == 'MostFrequentCategories':
        unqX2 = np.unique(X2, return_counts=True)
        aux = [(unqX2[0][i], unqX2[1][i])
               for i in range(len(unqX2[0]))]
        aux = sorted(aux, key=itemgetter(1))[::-1]
        unqX2 = np.array([aux[i][0] for i in range(d)])
        x_out = categorical_encoding(X1, unqX2, y_train, encoder, clf_type,
                                     n_jobs)
        col_value_list = [(col_name, j) for j in range(d)]
    if method == 'KMeans':
        x = categorical_encoding(unqX2, X2, y_train, encoder, clf_type,
                                 n_jobs)
        clustering = cluster.KMeans(n_clusters=d, random_state=11,
                                    copy_x=False)
        clustering.fit(x)
        centers = clustering.cluster_centers_
        dict_vectors = {cat: x[j, :]
                        for j, cat in enumerate(unqX2)}
        closest_centers = []
        for center in centers:
            closest_dist = np.infty
            closest_center = 0
            for cat in dict_vectors:
                if (closest_dist > np.linalg.norm(
                     center-dict_vectors[cat])):
                    closest_dist = (np.linalg.norm(center -
                                    dict_vectors[cat]))
                    closest_center = cat
            closest_centers.append(closest_center)
        x_out = categorical_encoding(X1, np.array(closest_centers),
                                     y_train,
                                     encoder, clf_type, n_jobs)
        col_value_list = [(col_name, j) for j in range(d)]
    if method == 'KMeans_clustering':
        x = categorical_encoding(unqX2, X2, y_train, encoder, clf_type,
                                 n_jobs)
        unqX1 = np.unique(X1)
        x1 = categorical_encoding(unqX1, X2, y_train, encoder, clf_type,
                                  n_jobs)
        clustering = cluster.KMeans(n_clusters=d, random_state=11,
                                    copy_x=False)
        index = clustering.fit_predict(x).astype(str)
        index1 = clustering.predict(x1).astype(str)
        SE = categorical_encoding(index1, np.unique(index), y_train,
                                  'one-hot', clf_type, n_jobs)
        x_out = np.zeros((len(X1), d))
        dict1 = {x: SE[i] for i, x in enumerate(unqX1)}
        for i, x in enumerate(X1):
            x_out[i] = dict1[x]
        col_value_list = [(col_name, j) for j in range(d)]
    if method == 'PCA':
        unqX1 = np.unique(X1)
        SE = categorical_encoding(unqX2, X2, y_train, encoder, clf_type,
                                  n_jobs)
        SE1 = categorical_encoding(unqX1, X2, y_train, encoder, clf_type,
                                   n_jobs)
        pca = decomposition.PCA(n_components=d,
                                random_state=87)
        pca.fit(SE)
        SE1 = pca.transform(SE1)
        x_out = np.zeros((len(X1), d))
        dict1 = {x: SE1[i] for i, x in enumerate(unqX1)}
        for i, x in enumerate(X1):
            x_out[i] = dict1[x]
        col_value_list = [(col_name, j) for j in range(d)]

    return x_out, col_value_list


def transformX(X1, X2, y_train, clf_type, method, xcols, encoder,
               dimension_reduction, n_jobs=1):
    """
    transform each column separately given an mapping of processing methods
    :param X1: test or training input set
    :param X2: test or training input set
    :param y_train:
    :param clf_type:
    :param method: list, transformation methods. num stands for numerical, ohe for one hot encoding, se for similarity
    encoding
    :param xcols:list gathering the names for each of the columns
    :param distance: distance used in se
    :param dimension_reduction: ?
    :param n_jobs:
    :return:
    """
    # could make the passing of distance optional since it is only used for similarity encoding
    res = [process_column(X1[:, i], X2[:, i], y_train, clf_type,
                          method[i], xcols[i], encoder,
                          n_jobs, dimension_reduction)
           for i in range(len(method))]
    X_out = ()
    col_value_list, shapes = [], []
    for r in res:
        x, y = r
        if x.shape[1] != 0:
            X_out += (x,)
            col_value_list += y
            shapes += [(None, len(y))]

    try:
        X_out = np.hstack(X_out).astype('float32')
    except ValueError:
        X_out = sparse.hstack(X_out).astype('float32')

    return X_out, col_value_list, shapes


def one_hot_encoding(X, unqY, n_jobs):
    # Xout = Parallel(n_jobs=n_jobs)(delayed(compare_strings)(x, unqX)
    #                                for x in X)
    unqX = np.unique(X)
    dict1 = {x: compare_strings(x, unqY) for x in unqX}
    X_out = np.zeros((len(X), len(unqY)))
    for i, x in enumerate(X):
        X_out[i] = dict1[x]
    return X_out


def arrayvalues2mat(X):
    Xout = np.vstack((x.reshape(1, -1) for x in X))
    print(Xout.shape)
    return Xout


def categorical_encoding(A, B, y_train, encoder, clf_type, n_jobs):
    '''Build the matrix of encoders.
    Given two arrays of strings to compare an a encoder, returns the
    corresponding encoder matrix of size len(A)xlen(B)'''

    if encoder == 'levenshtein-ratio_similarity':
        B = np.unique(B)
        unqA = np.unique(A)
        vlev = np.vectorize(lev.ratio)
        # dvec = Parallel(n_jobs=n_jobs)(delayed(vlev)(a, B.reshape(1, -1))
        #                           for a in unqA)
        dvec = [vlev(a, B.reshape(1, -1)) for a in unqA]
        ddict = {unqA[i]: dvec[i] for i in range(len(dvec))}
        dms = (ddict[a] for a in A)
        dm = np.vstack(dms)
        return dm
    if encoder == 'one-hot_encoding':
        B = np.unique(B)
        dm = one_hot_encoding(A, B, 1)
        return dm
    if encoder == 'one-hot_encoding_sparse':
        B = np.unique(B)
        dm = one_hot_encoding(A, B, 1)
        return sparse.csr_matrix(dm)
    if encoder == 'jaccard_similarity':
        B = np.unique(B)
        warning = (('Warning: %s is not a well defined similarity ' +
                    'metric because two different values can have a ' +
                    'similarity of 1') % encoder)
        print(warning)
        unqA = np.unique(A)
        vlev = np.vectorize(dist.jaccard)
        # dvec = Parallel(n_jobs=n_jobs)(delayed(vlev)(a, B.reshape(1, -1))
        #                           for a in unqA)
        dvec = [vlev(a, B.reshape(1, -1)) for a in unqA]
        ddict = {unqA[i]: dvec[i] for i in range(len(dvec))}
        dms = (ddict[a] for a in A)
        dm = np.vstack(dms)
        return 1 - dm
    if encoder == 'sorensen_similarity':
        B = np.unique(B)
        unqA = np.unique(A)
        vlev = np.vectorize(dist.sorensen)
        # dvec = Parallel(n_jobs=n_jobs)(delayed(vlev)(a, B.reshape(1, -1))
        #                           for a in unqA)
        dvec = [vlev(a, B.reshape(1, -1)) for a in unqA]
        ddict = {unqA[i]: dvec[i] for i in range(len(dvec))}
        dms = (ddict[a] for a in A)
        dm = np.vstack(dms)
        return 1 - dm
    if encoder == 'jaro-winkler_similarity':
        B = np.unique(B)
        unqA = np.unique(A)
        # vjw = np.vectorize(jwdistance.get_jaro_distance)
        vjw = np.vectorize(jellyfish.jaro_distance)
        # dvec = Parallel(n_jobs=n_jobs)(delayed(vlev)(a, B.reshape(1, -1))
        #                           for a in unqA)
        dvec = [vjw(a, B.reshape(1, -1)) for a in unqA]
        ddict = {unqA[i]: dvec[i] for i in range(len(dvec))}
        sms = (ddict[a] for a in A)
        sm = np.vstack(sms)
        return sm
    if encoder == '3gram_similarity':
        B = np.unique(B)
        unqA = np.unique(A)
        ngram_dict = dictionary_of_3grams(B)
        strings_len = strings_length(B)
        sm = np.zeros((len(A), len(B)))
        dict1 = {a: ngram_similarity(a, strings_len, ngram_dict) for a in unqA}
        for i, a in enumerate(A):
            sm[i] = dict1[a]
        return sm
    if encoder[1:] == 'gram_similarity1':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity1(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity2':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity2(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity2_theta':
        n = int(encoder[0])
        B, count = np.unique(B, return_counts=True)
        thetas = count/sum(count)
        sm = ngram_similarity2(A, B, n)
        sm = sm/thetas
        return sm
    if encoder[1:] == 'gram_presence_fisher_kernel':
        n = int(encoder[0])
        sm = ngram_presence_fisher_kernel(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity2_1':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity2_1(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity2_2':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity2_2(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity3':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity3(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity3_2':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity3_2(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity4':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity4(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity5':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity5(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity6':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity6(A, B, n)
        return sm
    if encoder[1:] == 'gram_similarity7':
        n = int(encoder[0])
        B = np.unique(B)
        sm = ngram_similarity7(A, B, n)
        return sm
    if encoder[1:] == 'grams_count_vectorizer':
        n = int(encoder[0])
        B = np.unique(B)
        vectorizer = CountVectorizer(analyzer='char', ngram_range=(n, n))
        vectorizer.fit(B)
        count_matrix1 = vectorizer.transform(A)
        return count_matrix1
    if encoder[1:] == 'grams_tfidf_vectorizer':
        n = int(encoder[0])
        B = np.unique(B)
        vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(n, n),
                                     smooth_idf=False)
        vectorizer.fit(B)
        tfidfA = vectorizer.transform(A)
        return tfidfA
    if encoder[1:] == 'grams_tf_vectorizer':
        n = int(encoder[0])
        B = np.unique(B)
        vectorizer = TfidfVectorizer(analyzer='char', ngram_range=(n, n),
                                     smooth_idf=False, use_idf=False)
        vectorizer.fit(B)
        tfidfA = vectorizer.transform(A)
        return tfidfA
    if encoder[1:] == 'grams_hot_vectorizer':
        n = int(encoder[0])
        B = np.unique(B)
        vectorizer = CountVectorizer(analyzer='char', ngram_range=(n, n))
        vectorizer.fit(B)
        count_matrix1 = vectorizer.transform(A)
        return (count_matrix1 > 0).astype('float64')
    if encoder[1:] == 'grams_hot_vectorizer_tfidf':
        n = int(encoder[0])
        B = np.unique(B)
        vectorizer = CountVectorizer(analyzer='char', ngram_range=(n, n))
        presenceB = (vectorizer.fit_transform(B) > 0).astype('float64')
        presenceA = (vectorizer.transform(A) > 0).astype('float64')
        transformer = TfidfTransformer(smooth_idf=True)
        transformer.fit(presenceB)
        tfidfA = transformer.transform(presenceA)
        return tfidfA
    if encoder[1:] == 'grams_hashing':
        n = int(encoder[0])
        hashingA = ngrams_hashing_vectorizer(A, n, 10000)
        return hashingA
    if encoder == 'TargetEncoding':
        def lambda_(x, n):
            return x / (x + n)
        counter = collections.Counter(B)
        unqA = np.unique(A)
        unqB = np.unique(B)
        n = len(y_train)
        k = len(unqB)
        encoder = {x: 0 for x in unqA}
        if clf_type in ['binary_clf', 'regression']:
            for x in unqA:
                y_train2 = y_train[B == x]
                if len(y_train2) == 0:
                    Eyx = 0
                else:
                    Eyx = np.mean(y_train[B == x])
                Ey = np.mean(y_train)
                lambda_n = lambda_(counter[x], n/k)
                encoder[x] = lambda_n*Eyx + (1 - lambda_n)*Ey
            x_out = np.zeros((len(A), 1))
            for i, x in enumerate(A):
                x_out[i, 0] = encoder[x]
        if clf_type in ['multiclass_clf']:
            x_out = np.zeros((len(A), len(np.unique(y_train))))
            lambda_n = {x: 0 for x in unqA}
            y_train2 = {x: 0 for x in unqA}
            for x in unqA:
                lambda_n[x] = lambda_(counter[x], n/k)
                y_train2[x] = y_train[B == x]
            for j, y in enumerate(np.unique(y_train)):
                Ey = sum(y_train == y)/n
                for x in unqA:
                    if len(y_train2[x]) == 0:
                        Eyx = 0
                    else:
                        Eyx = sum(y_train2[x] == y)/len(y_train2[x])
                    encoder[x] = lambda_n[x]*Eyx + (1 - lambda_n[x])*Ey
                for i, x in enumerate(A):
                    x_out[i, j] = encoder[x]
        print(x_out.shape)
        return x_out
    if encoder == 'BackwardDifferenceEncoder':
        encoder = ce.BackwardDifferenceEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'BinaryEncoder':
        encoder = ce.BinaryEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'HashingEncoder':
        encoder = ce.HashingEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'HelmertEncoder':
        encoder = ce.HelmertEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'OneHotEncoder':
        encoder = ce.OneHotEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'OrdinalEncoder':
        encoder = ce.OrdinalEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'SumEncoder':
        encoder = ce.SumEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'PolynomialEncoder':
        encoder = ce.PolynomialEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'BaseNEncoder':
        encoder = ce.BaseNEncoder()
        encoder.fit(B)
        se = encoder.transform(A)
        return se
    if encoder == 'LeaveOneOutEncoder':
        encoder = ce.LeaveOneOutEncoder()
        encoder.fit(B, y_train)
        se = encoder.transform(A)
        return se
    else:
        message = 'Encoder %s has not been implemented yet.' % encoder
        return message


def add_typo2string(word, typo_df):
    # only for adult dataset
    words = word.split('-')
    idx = np.random.choice(range(len(words)))
    changed = True
    try:
        words[idx] = np.random.choice(typo_df.loc[words[idx].lower().strip()
                                                  ].values.ravel())
    except Exception:
        changed = False
    return '-'.join(words), changed


def add_column_typos(df, col, typo_prob, typo_df, coln, n):
    rows = np.arange(n)
    np.random.seed(coln)
    np.random.shuffle(rows)
    print('Adding typos to column: ' + col)
    i = 0
    ok = True
    new_words = []
    for row in rows:
        ok = (i+1)/n >= typo_prob
        if ok:
            break
        new_word, changed = add_typo2string(df.loc[row, col], typo_df)
        if changed:
            new_words.append((row, new_word))
            i += 1

    rows = [a[0] for a in new_words]
    new_words = [a[1] for a in new_words]
    return (col, rows, new_words)


def add_typos(df, cols, typo_prob, typo_df, n_jobs):
    n = float(len(df))
    res = Parallel(n_jobs=n_jobs)(delayed(add_column_typos)
                                  (df, col, typo_prob, typo_df, coln, n)
                                  for coln, col in enumerate(cols))
    for col, rows, new_words in res:
        df.loc[rows, col] = new_words
    return df


def sentence_vector_avg(sentence, glove):
    """Calculate the sentence vector as the mean of the word vectors"""
    word_vecs = []
    for token in sentence:
        token = token.lower()
        try:
            word_vecs.append(np.array(glove[token]))
        except KeyError:
            pass

    return np.array(word_vecs).mean(axis=0)


def embed_avg(sentences):
    """Calculate sentence embeddings for set of sentences
    based on the average of the word vectors
    """
    values = []
    for s in sentences:
        mean = sentence_vector_avg(s)
        values.append(mean)
    return np.array(values)


def predict_fold(MX, y, train_index, test_index, method, xcols, dataset,
                 encoder, fold, n_splits, clf, clf_type, scaler,
                 dimension_reduction, configs=None):
    """
    fits and predicts a X with y given multiple parameters. (should maybe be called fit_predict?)
    :param MX:
    :param y:
    :param train_index:
    :param test_index:
    :param method:
    :param xcols:
    :param dataset:
    :param distance:
    :param fold:
    :param n_splits:
    :param clf:
    :param clf_type: RegressorMixin, ClassifierMixin
    :param scaler:
    :param dimension_reduction:
    :return:
    """
    start = time.time()
    method = [method[key] for key in xcols]
    MX_train, MX_test = MX[train_index], MX[test_index]
    y_train, y_test = y[train_index], y[test_index]
    X_test, col_names, shapes = transformX(MX_test, MX_train, y_train, clf_type,
                                           method,
                                           xcols, encoder,
                                           dimension_reduction,
                                           n_jobs=1)
    del col_names

    X_train, col_names, shapes = transformX(MX_train, MX_train, y_train, clf_type,
                                            method,
                                            xcols, encoder,
                                            dimension_reduction,
                                            n_jobs=1)
    del MX, MX_train, MX_test

    results = []
    encoding_time = time.time()-start
    X_train = scaler.fit_transform(X_train)
    X_test = scaler.transform(X_test)
    print('Split (%d/%d), Encoding: OK; Time: %.0f seconds'
          % (fold, n_splits, encoding_time))


    start = time.time()
    if isinstance(clf, NNetEstimator):
        configs = append_input_shape_to_configs(shapes, configs, rescale_layer_number=True)
        clf.fit(X_train, y_train, configs)
    else:
        clf.fit(X_train, y_train)
    training_time = time.time() - start
    train_shape = X_train.shape
    del X_train

    if clf_type == 'regression':
        y_pred = clf.predict(X_test)
        score = metrics.r2_score(y_test, y_pred)
        print('Fold (%d/%d), ' % (fold, n_splits),
              'dist: %s, ' % encoder,
              'dataset: %s, ' % dataset,
              'n_samp: %d, ' % train_shape[0],
              'n_feat: %d, ' % train_shape[1],
              'r2: %.4f, ' % score,
              'train-time: %.0f s.' % training_time)
    if clf_type == 'binary_clf':
        if isinstance(clf, NNetBinaryClassifier):
            y_pred = clf.predict_proba(X_test)
        else:
            try:
                y_pred = clf.predict_proba(X_test)[:, 1]
            except AttributeError:
                y_pred = clf.decision_function(X_test)
        score = metrics.average_precision_score(y_test, y_pred)
        print('Split (%d/%d), ' % (fold, n_splits),
              'dist: %s, ' % encoder,
              'dataset: %s, ' % dataset,
              'n_samp: %d, ' % train_shape[0],
              'n_feat: %d, ' % train_shape[1],
              'av-prec: %.4f, ' % score,
              'train-time: %.0f s.' % training_time)
    if clf_type == 'multiclass_clf':
        y_pred = clf.predict(X_test)
        score = metrics.accuracy_score(y_test, y_pred)
        print('Split (%d/%d), ' % (fold, n_splits),
              'dist: %s, ' % encoder,
              'dataset: %s, ' % dataset,
              'n_samp: %d, ' % train_shape[0],
              'n_feat: %d, ' % train_shape[1],
              'accuracy: %.4f, ' % score,
              'train-time: %.0f s.' % training_time)
    results.append([fold, y_train.shape[0], X_test.shape[1],
                    score, encoding_time, training_time])
    return results


def results_parameters(file_path):
    '''Return a dictionary with parameters given a result file.'''
    filename = file_path.split('/')[-1]
    params = {val.split('-')[0]: '-'.join(val.split('-')[1:])
              for val in filename.split('_')}
    return params


def file_meet_conditions(dataset, files, conditions):
    '''Return:
    True if all conditions for are meet for some results file.
    False if not.'''
    file_ok = []
    for f in files:
        params = results_parameters(f)
        cond = True
        for key in conditions:
            if key == 'Classifier':
                cond *= (conditions[key] in params[key])
            else:
                cond *= (conditions[key] == params[key])
        if cond:
            file_ok.append(f)

    if len(file_ok) > 0:
        return file_ok, params
    elif len(file_ok) == 0:
        raise NameError('No file meets all conditions for dataset:', dataset)
    else:
        raise NameError('???')


def file_meet_conditions2(files, conditions):
    '''Return:
    True if all conditions are meet for some file.
    False if not.'''
    file_ok = []
    for f in files:
        params = read_json(f)
        cond_final = True
        for key in conditions:
            if key == 'clf':
                cond = max([(c in params[key][0]) for c in conditions[key]])
            elif key == 'encoder':
                cond = (params[key] in conditions[key])
            else:
                cond = (params[key] == conditions[key])
            cond_final *= cond
            # if cond is False:
            #     print('problem!')
            #     print(params[key])
            #     print(conditions[key])
            #     print('\n')
        if cond_final:
            file_ok.append(f)
    return file_ok


def write_pickle(data, file):
    with open(file, 'wb') as f:
        pickle.dump(data, f)


def read_pickle(file):
    with open(file, 'rb') as f:
        data = pickle.load(f)
    return data


def read_all_pickles(folder):
    files = glob.glob(os.path.join(folder, '*'))
    data = []
    for file_ in files:
        data.append(read_pickle(file_))
    return data


def write_json(data, file):
    with open(file, 'w') as f:
        json.dump(data, f, ensure_ascii=False, sort_keys=True, indent=4)


def read_json(file):
    with open(file, 'r') as f:
        data = json.load(f)
    return data


def read_all_json(folder):
    files = glob.glob(os.path.join(folder, '*.json'))
    data = []
    for file_ in files:
        data.append(read_json(file_))
    return data


def tuple2list(dict_):
    if type(dict_) is dict:
        for k in dict_:
            if type(dict_[k]) is dict:
                dict_[k] = tuple2list(dict_[k])
            elif type(dict_[k]) is tuple:
                dict_[k] = list(dict_[k])
            elif type(dict_[k]) is list:
                for i, j in enumerate(dict_[k]):
                    dict_[k][i] = tuple2list(dict_[k][i])
    return dict_


def verify_if_exists(results_path, results_dict):
    results_dict = tuple2list(results_dict)
    files = glob.glob(os.path.join(results_path, '*.json'))
    # files = [os.path.join(results_path, 'drago2_20170925151218997989.json')]
    for file_ in files:
        data = read_json(file_)
        params_dict = {k: data[k] for k in data
                       if k not in ['results']}
        if params_dict == results_dict:
            return True
        # else:
        #     for k in params_dict:
        #         if params_dict[k] != results_dict[k]:
        #             print(params_dict[k])
        #             print(results_dict[k])
        #             print('\n')
    return False


def random_combination(iterable, n, r):
    "Random selection from itertools.combinations(iterable, r)"
    pool = tuple(iterable)
    m = len(pool)
    np.random.seed(seed=24)
    indices = np.random.choice(range(m), (n, r))
    result = []
    for index in indices:
        result.append(tuple(pool[i] for i in index))
    return result


def average_ranking(X):
    ranking = np.zeros(len(X))
    for i in range(len(X[0])):
        x = np.array([X[j][i] for j in range(len(X))])
        ranking += np.argsort(np.argsort(x)[::-1]) + 1
    ranking = ranking/len(X[0])
    return ranking
