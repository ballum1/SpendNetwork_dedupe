#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
This code uses RecordLink on two CSV files, one for unmatched suppliers for usm3, one for suppliers from the supplier table.
The RecordLink matching only finds clusters on 1:1 level (i.e. matches a single supplier string from usm3 to a single supplier from the supplier table).

The output will be a CSV with the linked results. "Output_cleanup.py" can be used to make the results a bit more readable.

Change the data paths in the setup section to run the matching between different files.
Change (or delete) the settings and json files in the setup section to re-train the matcher.

"""
from __future__ import print_function
from future.builtins import next

import os
import csv
import re
import collections
import logging
import optparse
import numpy
import pandas as pd

import dedupe
from unidecode import unidecode

# ## Logging

# dedupe uses Python logging to show or suppress verbose output. Added for convenience.
# To enable verbose logging, run `python examples/csv_example/csv_example.py -v`
optp = optparse.OptionParser()
optp.add_option('-v', '--verbose', dest='verbose', action='count',
                help='Increase verbosity (specify multiple times for more)'
                )
(opts, args) = optp.parse_args()
log_level = logging.WARNING 
if opts.verbose :
    if opts.verbose == 1:
        log_level = logging.INFO
    elif opts.verbose >= 2:
        log_level = logging.DEBUG
logging.getLogger().setLevel(log_level)


# ## Setup

output_file = 'AC_data_matching_output.csv'
settings_file = 'data_matching_learned_settings'
training_file = 'data_matching_training.json'

data_1_path = 'AC_unmatched_usm3.csv'
data_0_path = 'AC_suppliers.csv'

single_line_per_cluster = True # make this true if you want side-by-side comparison in output

def preProcess(column):
    """
    Do a little bit of data cleaning with the help of Unidecode and Regex.
    Things like casing, extra spaces, quotes and new lines can be ignored.
    """

    column = unidecode(column)
    column = re.sub('\n', ' ', column)
    column = re.sub('-', '', column)
    column = re.sub('/', ' ', column)
    column = re.sub("'", '', column)
    column = re.sub(",", '', column)
    column = re.sub(":", ' ', column)
    column = re.sub('  +', ' ', column)
    column = column.strip().strip('"').strip("'").lower().strip()
    if not column :
        column = None
    return column


def readData(filename):
    """
    Read in our data from a CSV file and create a dictionary of records, 
    where the key is a unique record ID.
    """

    data_d = {}

    with open(filename) as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            clean_row = dict([(k, preProcess(v)) for (k, v) in row.items()])
            # if clean_row['price'] :
            #     clean_row['price'] = float(clean_row['price'][1:])
            data_d[filename + str(i)] = dict(clean_row)

    return data_d

    
print('importing data ...')
data_1 = readData(data_1_path)  #NOTE: later on 0 will be the usm3 unmatched and 1 will be the suppliers
data_2 = readData(data_0_path)

def descriptions() :
    for dataset in (data_1, data_2) :
        for record in dataset.values() :
            yield record['description']

# ## Training


if os.path.exists(settings_file):
    print('reading from', settings_file)
    with open(settings_file, 'rb') as sf :
        linker = dedupe.StaticRecordLink(sf)

else:
    # Define the fields the linker will pay attention to
    #
    # Notice how we are telling the linker to use a custom field comparator
    # for the 'price' field.
    fields = [
        {'field' : 'sss', 'type': 'String'}
    ]

    # Create a new linker object and pass our data model to it.
    linker = dedupe.RecordLink(fields)
    # To train the linker, we feed it a sample of records.
    linker.sample(data_1, data_2, 15000)

    # If we have training data saved from a previous run of linker,
    # look for it an load it in.
    # __Note:__ if you want to train from scratch, delete the training_file
    if os.path.exists(training_file):
        print('reading labeled examples from ', training_file)
        with open(training_file) as tf :
            linker.readTraining(tf)

    # ## Active learning
    # Dedupe will find the next pair of records
    # it is least certain about and ask you to label them as matches
    # or not.
    # use 'y', 'n' and 'u' keys to flag duplicates
    # press 'f' when you are finished
    print('starting active labeling...')

    dedupe.consoleLabel(linker)

    linker.train()

    # When finished, save our training away to disk
    with open(training_file, 'w') as tf :
        linker.writeTraining(tf)

    # Save our weights and predicates to disk.  If the settings file
    # exists, we will skip all the training and learning next time we run
    # this file.
    with open(settings_file, 'wb') as sf :
        linker.writeSettings(sf)


# ## Blocking

# ## Clustering

# Find the threshold that will maximize a weighted average of our
# precision and recall.  When we set the recall weight to 2, we are
# saying we care twice as much about recall as we do precision.
#
# If we had more data, we would not pass in all the blocked data into
# this function but a representative sample.

print('clustering...')
linked_records = linker.match(data_1, data_2, 0)

print('# duplicate sets', len(linked_records))

# ## Writing Results

# Write our original data back out to a CSV with a new column called 
# 'Cluster ID' which indicates which records refer to each other.

cluster_membership = {}
cluster_id = None
for cluster_id, (cluster, score) in enumerate(linked_records):
    for record_id in cluster:
        cluster_membership[record_id] = (cluster_id, score)

if cluster_id :
    unique_id = cluster_id + 1
else :
    unique_id =0
    

with open(output_file, 'w') as f:
    writer = csv.writer(f)
    
    header_unwritten = True

    for fileno, filename in enumerate((data_0_path, data_1_path)) :
        with open(filename) as f_input :
            reader = csv.reader(f_input)

            if header_unwritten :
                heading_row = next(reader)
                heading_row.insert(0, 'source_file')
                heading_row.insert(0, 'link_score')
                heading_row.insert(0, 'cluster_id')
                writer.writerow(heading_row)
                header_unwritten = False
            else :
                next(reader)

            for row_id, row in enumerate(reader):
                cluster_details = cluster_membership.get(filename + str(row_id))
                if cluster_details is None :
                    cluster_id = unique_id
                    unique_id += 1
                    score = None
                else :
                    cluster_id, score = cluster_details
                row.insert(0, fileno)
                row.insert(0, score)
                row.insert(0, cluster_id)
                writer.writerow(row)

# temporary workaround to get each cluster on a single line

if single_line_per_cluster:
    print("converting output to single cluster per line format...")
    df = pd.read_csv(output_file)
    df_sss = df_sss = df.pivot(index = "cluster_id", columns="source_file", values="sss")
    df_link_score = df[["cluster_id", "link_score"]]
    df_link_score = df_link_score.sort_values(by="cluster_id")
    df_link_score = df_link_score.drop_duplicates()
    df_link_score.set_index("cluster_id")

    df_converted = pd.concat([df_link_score, df_sss], axis=1)
    df_converted.to_csv(output_file)