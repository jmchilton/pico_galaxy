#!/usr/bin/env python
"""Implements assorted RXLR motif methods from the literature

This script takes exactly four command line arguments:
 * Protein FASTA filename
 * Number of threads
 * Model name (Bhattacharjee2006, Win2007, Whisson2007re)
 * Output tabular filename

The model names are:

Bhattacharjee2006: Simple regular expression search for RXLR
with additional requirements for positioning and signal peptide.

Win2007: Simple regular expression search for RXLR, but with
different positional requirements.

Whisson2007re: As Bhattacharjee2006 but with a more complex regular
expression to look for RXLR-EER domain.

See the help text in the accompanying Galaxy tool XML file for more
details including the full references.

Note:

Bhattacharjee et al. (2006) and Win et al. (2007) used SignalP v2.0,
which is no longer available. The current release is SignalP v3.0
(Mar 5, 2007). We have therefore opted to use the NN Ymax position for
the predicted cleavage site, as this is expected to be more accurate.
Also note that the HMM score values have changed from v2.0 to v3.0.
Whisson et al. (2007) used SignalP v3.0 anyway.
"""
import os
import sys
import re
from seq_analysis_utils import stop_err, fasta_iterator

if len(sys.argv) != 5:
   stop_err("Requires four arguments: protein FASTA filename, threads, model, and output filename")

fasta_file, threads, model, tabular_file = sys.argv[1:]
signalp_input_file = tabular_file + ".fasta.tmp"
signalp_output_file = tabular_file + ".tabular.tmp"
signalp_trunc = 70
min_hmm = 0.9

if model == "Bhattacharjee2006":
   re_rxlr = re.compile("R.LR")
   min_sp = 10
   max_sp = 40
   max_sp_rxlr = 100
   min_rxlr_start = 1
   #Allow signal peptide to be at most 40aa, and want RXLR to be
   #within 100aa, therefore for the prescreen the max start is 140:
   max_rxlr_start = max_sp + max_sp_rxlr
elif model == "Win2007":
   re_rxlr = re.compile("R.LR")
   min_sp = 10
   max_sp = 40
   min_rxlr_start = 30
   max_rxlr_start = 60
   #No explicit limit on separation of signal peptide clevage
   #and RXLR, but shortest signal peptide is 10, and furthest
   #away RXLR is 60, so effectively limit is 50.
   max_sp_rxlr = max_rxlr_start - min_sp + 1
elif model == "Whisson2007re":
   re_rxlr = re.compile("R.LR.{,40}[ED][ED][KR]")
   min_sp = 10
   max_sp = 40
   max_sp_rxlr = 100
   min_rxlr_start = 1
   max_rxlr_start = max_sp + max_sp_rxlr
else:
   stop_err("Did not recognise the model name %r\n"
            "Use Bhattacharjee2006, Win2007, or Whisson2007re" % model)


#Prepare short list of candidates containing RXLR to pass to SignalP
assert min_rxlr_start > 0, "Min value one, since zero based counting"
count = 0
total = 0
handle = open(signalp_input_file, "w")
for title, seq in fasta_iterator(fasta_file):
    total += 1
    name = title.split(None,1)[0]
    match = re_rxlr.search(seq[min_rxlr_start-1:].upper())
    if match and min_rxlr_start - 1 + match.start() + 1 <= max_rxlr_start:
        #This is a potential RXLR, depending on the SignalP results.
        #Might as well truncate the sequence now, makes the temp file smaller
        handle.write(">%s (truncated)\n%s\n" % (name, seq[:signalp_trunc]))
        count += 1
handle.close()
print "Running SignalP on %i/%i potentials." % (count, total)


#Run SignalP (using our wrapper script to get multi-core support etc)
signalp_script = os.path.join(os.path.split(sys.argv[0])[0], "signalp3.py")
if not os.path.isfile(signalp_script):
    stop_err("Error - missing signalp3.py script")
cmd = "python %s euk %i %s %s %s" % (signalp_script, signalp_trunc, threads, signalp_input_file, signalp_output_file)
return_code = os.system(cmd)
if return_code:
    stop_err("Error %i from SignalP:\n%s" % (return_code, cmd))


def parse_signalp(filename):
    """Parse SignalP output, yield tuples of ID, HMM_Sprob_score and NN predicted signal peptide length.

    For signal peptide length we use NN_Ymax_pos (minus one).
    """
    handle = open(filename)
    line = handle.readline()
    assert line.startswith("#ID\t"), line
    for line in handle:
        parts = line.rstrip("\t").split("\t")
        assert len(parts)==20, repr(line)
        yield parts[0], float(parts[18]), int(parts[5])-1
    handle.close()


#Parse SignalP results and apply the strict RXLR criteria
count = 0
total = 0
handle = open(tabular_file, "w")
handle.write("#ID\t%s\n" % model)
signalp_results = parse_signalp(signalp_output_file)
for title, seq in fasta_iterator(fasta_file):
    total += 1
    rxlr = "N"
    name = title.split(None,1)[0]
    match = re_rxlr.search(seq[min_rxlr_start-1:].upper())
    if match and min_rxlr_start - 1 + match.start() + 1 <= max_rxlr_start:
        del match
        #This was the criteria for calling SignalP,
        #so it will be in the SignalP results.
        sp_id, sp_hmm_score, sp_nn_len = signalp_results.next()
        assert name == sp_id, "%s vs %s" % (name, sp_id)
        #if name == "Hp_Contig1403.2_F21":
        #    print name, sp_hmm_score, sp_nn_len
        if sp_hmm_score >= min_hmm and min_sp <= sp_nn_len <= max_sp:
            match = re_rxlr.search(seq[sp_nn_len:].upper())
            if match and match.start() + 1 <= max_sp_rxlr: #1-based counting
                rxlr_start = sp_nn_len + match.start() + 1
                if min_rxlr_start <= rxlr_start <= max_rxlr_start:
                    rxlr = "Y"
                    count += 1
    handle.write("%s\t%s\n" % (name, rxlr))
handle.close()

#Check the iterator is finished
try:
    signalp_results.next()
    assert False, "Unexpected data in SignalP output"
except StopIteration:
    pass

#Cleanup
os.remove(signalp_input_file)
os.remove(signalp_output_file)

#Short summary to stdout for Galaxy's info display
print "%i out of %i have %s RXLR motif" % (count, total, model)