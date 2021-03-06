# -*- coding: utf-8 -*-
"""
pgswl_record_linkage pulls data from usm3 and suppliers from the database,
uses dedupes record_linkage to find matches between usm3 and suppliers,
uploads the matches (clusters) to table
"""

import dedupe
import sys
import os
import re
import collections
import time
import logging
import optparse
from dotenv import load_dotenv, find_dotenv
import psycopg2 as psy
import psycopg2.extras
from unidecode import unidecode

# parser for debugging
optp = optparse.OptionParser()
optp.add_option('-v', '--verbose', dest='verbose', action='count',
                help='Increase verbosity (specify multiple times for more)'
                )
(opts, args) = optp.parse_args()
log_level = logging.WARNING 
if opts.verbose == 1:
    log_level = logging.INFO
elif opts.verbose >= 2:
    log_level = logging.DEBUG
logging.getLogger().setLevel(log_level)

# settings and training files
settings_file = 'data_matching_learned_settings'
training_file = 'data_matching_training.json'

table_name = "usm3_suppliers_matched"
table_schema = "blue"

column_names = ["cluster_id", "id", "sss", "rid", "supplier_name"]

# select alphabetic segment of table you want to dedupe
alphabetic_filter = "AB%"

# local database details (to use when testing)
dbname = "postgres"
user = "postgres"
password = "postgres"
host = "host"

# get the remote database details from .env
load_dotenv(find_dotenv())
host_remote = os.environ.get("HOST_REMOTE")
dbname_remote = os.environ.get("DBNAME_REMOTE")
user_remote = os.environ.get("USER_REMOTE")
password_remote = os.environ.get("PASSWORD_REMOTE")

start_time = time.time()

# TWO SEPARATE CONNECTION SESSIONS
# the first to be used for fetching the data (or rather the fields that are used for dedupe)
con1 = psy.connect(host=host_remote, dbname=dbname_remote, user=user_remote, password=password_remote)

# dictionary cursor, allows data retrieval using dicts
c1 = con1.cursor(cursor_factory=psy.extras.RealDictCursor)

SELECT_DATA_0 = "SELECT id, sss FROM blue.usm3 WHERE (sss LIKE '{}') AND (sid IS NULL)".format(alphabetic_filter)
SELECT_DATA_1 = "SELECT rid AS id, supplier_name AS sss FROM blue.supplier WHERE (supplier_name LIKE '{}') AND (supplier_id IS NOT NULL)".format(alphabetic_filter)

def preProcess(column):
    # takes in the key, value pair from data_select - then processes them for deduping later
    try:  # python 2/3 string differences
        column = column.decode('utf8')
    except AttributeError:
        pass
    if not isinstance(column, int):
        if not column:
            column = None
        else:
            # get rid of spaces/newlines
            column = unidecode(column)
            column = re.sub('  +', ' ', column)
            column = re.sub('\n', ' ', column)
            column = column.strip().strip('"').strip("'").lower().strip()
    return column

data_d0 = {}
data_d1 = {}
data_list = [data_d0, data_d1] # list to hold both dictionaries needed for deduping

for i, query in enumerate([SELECT_DATA_0, SELECT_DATA_1]):
    print "importing dataset {}...".format(str(i))
    c1.execute(query)
    data = c1.fetchall()
    for row in data:
        # each row is a dictionary
        clean_row = [(k, preProcess(v)) for (k, v) in row.items()]  # what are the keys and values here? are the keys each field name
        row_id = row['id']  # think i'd need to edit this if we don't have id
        data_list[i][row_id] = dict(clean_row)  # not sure exactly why we undictionaried and then dictionaried cleanrow...

# close conection
con1.close()

if os.path.exists(settings_file):
    print 'reading from', settings_file
    with open(settings_file) as sf :
        linker = dedupe.StaticRecordLink(sf)

else:
    fields = [
        {'field' : 'sss', 'type': 'String'}
        ]

    linker = dedupe.RecordLink(fields)
    # deduper = dedupe.Dedupe(fields)

    linker.sample(data_list[0], data_list[1], 15000)

    if os.path.exists(training_file):
        print 'reading labeled examples from ', training_file
        with open(training_file) as tf :
            linker.readTraining(tf)

    print 'starting active labeling...'

    dedupe.consoleLabel(linker)

    linker.train()
    
    with open(training_file, 'w') as tf :
        linker.writeTraining(tf)

    with open(settings_file, 'w') as sf :
        linker.writeSettings(sf)


print 'clustering...'
clustered_dupes = linker.match(data_list[0], data_list[1], threshold=0.5)

print '# duplicate sets', len(clustered_dupes)

print clustered_dupes


### for data source 0 (usm3), get the stuff to

SELECT_DATA_0 = "SELECT id, sss FROM blue.usm3 WHERE (sss LIKE '{}') AND (sid IS NULL)".format(alphabetic_filter)
SELECT_DATA_1 = "SELECT rid AS id, supplier_name AS sss FROM blue.supplier WHERE (supplier_name LIKE '{}') AND (supplier_id IS NOT NULL) AND (rid IS NOT NULL)".format(alphabetic_filter)



con2 = psy.connect(host=host_remote, dbname=dbname_remote, user=user_remote, password=password_remote)

# Select all the rows for some reason
c2 = con2.cursor()
c2.execute(SELECT_DATA_0)
data0 = c2.fetchall()

c2.execute(SELECT_DATA_1)
data1 = c2.fetchall()

full_data = []

print data0
print data1

cluster_membership = collections.defaultdict(lambda : 'x') #?
for cluster_id, (cluster, score) in enumerate(clustered_dupes):
    for datasource, record_id in enumerate(cluster):
        # treat the two separate record ids differently - i.e. use different data for next step from the different queries
        if datasource == 0:
            # if the id we're looking at is for usm3
            for row in data0:
                if record_id == int(row[0]):
                    row = list(row)
                    row.insert(0,cluster_id)
                    # add two blank rows on the end to cover rid and supplier name
                    row = row + [None, None]
                    row = tuple(row)
                    full_data.append(row)
        if datasource == 1:
            # if the id we're looking at is for suppliers table
            for row in data1:
                if record_id == int(row[0]):
                    row = list(row)
                    row.insert(0,cluster_id)
                    # add two blanks to cover id and sss
                    row.insert(1, None)
                    row.insert(1, None)
                    row = tuple(row)
                    full_data.append(row)


# create the results table
print ('creating results table {}...'.format(table_name))
c2.execute('DROP TABLE IF EXISTS {}.{}'.format(table_schema, table_name))  # get rid of the table (so we can make a new one)
field_string = ','.join('%s varchar(500000)' % name for name in column_names)
c2.execute('CREATE TABLE {}.{} ({})'.format(table_schema, table_name, field_string))
con2.commit()


num_cols = len(column_names)

# mogrify if just a way of putting variables into

mog = "(" + ("%s,"*(num_cols -1)) + "%s)"
args_str = ','.join(c2.mogrify(mog,x) for x in full_data) # This is the actual data that goes in the table
values = "("+ ','.join(x for x in column_names) +")"
c2.execute("INSERT INTO {}.{} {} VALUES {}".format(table_schema, table_name, values, args_str))
con2.commit()
con2.close()

print 'ran in', time.time() - start_time, 'seconds'
