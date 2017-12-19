### General thoughts:

It seems to me that dedupe is potentially a useful tool for matching suppliers. My results from record_linkage
(and potentially gazetteer) show that it can be used to match a high proportion (up to 50/60%?) of supplier strings.

However since at the moment the matching is only on a single field (supplier string), I don't think we're using dedupe to full potential.
Essentially I think we're using it as a sophisticated string matcher. That may be good enough for our purposes, but worth
bearing in mind that it has its limitations. (There is the possibility to improve this by using postcodes for at least some of the
unmatched supplier strings.)

### Input data:

For record_linkage and gazetteer, testing has mainly been done using unmatched AB and AC supplier strings from usm3,
and correspondingly, AB and AC suppliers from the supplier table (i.e. the master list of suppliers).

In terms of number of records:

unmatched usm3 "AB..." = 2.2k
suppliers "AB..." = 22k

unmatched usm "AC.." = 2.5k
suppliers "AC..." 26k

### Training:

The matcher for record_linkage and gazetteer has been trained using roughly 40 matching examples (20 negative matches, 20 positive matches)
that were generated by dedupe using the "AB..." datasets.

There is the possibility in due course to use our (vast) number of confirmed matches as training data in the future.
This may help with clustering hit rate/accuracy, although given the limitations of matching on a single field I'm not sure how
much more sophisticated we can make the matcher in practice

### Record_linkage results:

for AB:
clustered roughly 1145/2200 of the unmatched usm3 AB supplier strings (52%)
roughly 900 of these (41%) at score of 0.5 or above.
(several hundred of these appear to be exact string matches however)

for AC:
clustered roughly 1.5k/2.5k of the unmatched usm3 AC supplier strings (60%)
roughly 1100(44%) at score of 0.5 or above.

### gazetteer results:

I had difficulty getting this working and the results could probably be presented a little better.

From the first cleaned output file you can see the clusters between the datasets.
From the second cleaned output file you can see how many of the usm3 records were put into a cluster

You can see that, in contrast to the record_linkage, multiple records from usm3 could be put into a single cluster
(see e.g. clusters 28, 32, 33, 37 in gazetteer_output_AB_cleaned1.csv)

for AB:
1269/2200 of usm3 supplier strings were matched (slight improvement on record_linkage now the 1:1 restraint is removed)

for AC:
1.7k/2.5k of usm3 supplier strings were clustered (again, slight improvement on record_linkage)












