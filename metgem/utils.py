# Utility scripts
#

import sys
import os
import logging
from os.path import abspath, dirname, isdir, join, exists
from collections import defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

from enum import Enum

# Setup log
class colr:
    GRN = "\033[92m"
    END = "\033[0m"
    WARN = "\033[93m"


def setupLogging(LOGNAME):
    global log
    if "darwin" in sys.platform:
        stdoutformat = logging.Formatter(
            colr.GRN + "%(asctime)s" + colr.END + ": %(message)s",
            datefmt="[%b %d %I:%M %p]",
        )
    else:
        stdoutformat = logging.Formatter(
            "%(asctime)s: %(message)s", datefmt="[%I:%M %p]"
        )
    fileformat = logging.Formatter("%(asctime)s: %(message)s", datefmt="[%x %H:%M:%S]")
    log = logging.getLogger(__name__)
    log.setLevel(logging.DEBUG)
    sth = logging.StreamHandler()
    sth.setLevel(logging.INFO)
    sth.setFormatter(stdoutformat)
    log.addHandler(sth)
    fhnd = logging.FileHandler(LOGNAME)
    fhnd.setLevel(logging.DEBUG)
    fhnd.setFormatter(fileformat)
    log.addHandler(fhnd)


class TaxonomicLevel(Enum):
    kingdom = 1
    phylum = 2
    _class = 3
    order = 4
    famliy = 5
    genus = 6
    species = 7


def which(file):
    for path in os.environ["PATH"].split(os.pathsep):
        if os.path.exists(os.path.join(path, file)):
            return os.path.join(path, file)

    return None


def make_output_dir(dirpath, strict=False):
    """Make an output directory if it doesn't exist
    Returns the path to the directory
    dirpath -- a string describing the path to the directory
    strict -- if True, raise an exception if dir already
    exists
    """
    dirpath = abspath(dirpath)

    # Check if directory already exists
    if isdir(dirpath):
        if strict:
            err_str = "Directory '%s' already exists" % dirpath
            raise IOError(err_str)

        return dirpath
    try:
        os.makedirs(dirpath)
    except IOError as e:
        err_str = (
            "Could not create directory '%s'. Are permissions set "
            + "correctly? Got error: '%s'" % e
        )
        raise IOError(err_str)

    return dirpath


def read_otutable(fh):
    """Read OTU table file"""
    df = pd.read_csv(fh, sep="\t", header=0, index_col=0)
    return df


def read_taxatable(fh):
    """Read taxa table from QIIME. Currently only work on Greengene's notation"""
    alignment = ["kingdom", "phylum", "class", "order", "family", "genus", "species"]
    predf = pd.read_csv(fh, sep="\t", index_col=0, header=0)
    taxondf = pd.DataFrame.from_records(predf.Taxon.apply(gg_parse)).reindex(
        columns=alignment
    )
    taxondf.index = predf.index
    df = pd.concat([taxondf, predf["Confidence"]], axis=1)
    return df


def read_16s_table(file: Path):
    """Read 16s data as series"""
    normRNA = pd.read_csv(file, sep="\t", index_col=0, squeeze=True).fillna(1).clip(1)
    normRNA.name = "rna_n"
    return normRNA


def read_m2f(fh):
    """Read model2function. Keep NA since some analysis need it."""
    df = pd.read_csv(fh, sep="\t", index_col=0, header=0)
    return df


class TaxaStringError(ValueError):
    pass


def align_dataframe(main, converter):
    """Align index / column for dot calculation.

    Align B/A for convert A/Sample into B/Sample.
    While pandas ok with unsorted, the dimension has to be compatible.

    """
    # Make sure that they are at least compatible, at least 1 intersection
    MAINIDX = set(main.index).intersection(converter.columns)
    assert len(MAINIDX) / len(main.index) > 0

    main = main.reindex(index=MAINIDX)
    converter = converter.reindex(columns=MAINIDX)

    return (main, converter)


def gg_parse(s):
    """Parse taxonomy string in GG format. Return 7 levels of taxonomy.

    This methods it use to parsing the taxonomy string in greengene format ().
    In a case where the sequence does not have enough resolution, that taxnomic
    level will be shows as empty string.

        Args:
            s: taxonomy string in gg format (k__Kingdom; p__Phylum)

    """

    # TODO: Make it all lowercase
    abbr_dct = {
        "k": "kingdom",
        "p": "phylum",
        "c": "class",
        "o": "order",
        "f": "family",
        "g": "genus",
        "s": "species",
    }
    taxa_dct = {
        "kingdom": "",
        "phylum": "",
        "class": "",
        "order": "",
        "family": "",
        "genus": "",
        "species": "",
    }  # Because groupby exclude None value.
    items = s.split("; ")

    # Sanity check
    if not s.startswith("k__"):
        # Unidentified OTU
        return taxa_dct

    if len(items) > 7:
        raise TaxaStringError(
            "Input does not seems to be in GreenGene's format: {}".format(s)
        )

    # End sanity check

    for token in items:
        abbrv, taxa = token.split("__")
        taxa_lvl = abbr_dct[abbrv]
        taxa = taxa if taxa else ""  # If empty, leave it as empty string
        # If it is bracket, then remove it
        if len(taxa) > 0 and taxa[0] == "[" and taxa[-1] == "]":
            taxa = taxa[1:-1]

        taxa_dct[taxa_lvl] = taxa

    # Create species name since GG omit genus part
    if taxa_dct["genus"] != "" and taxa_dct["species"] != "":
        taxa_dct["species"] = taxa_dct["genus"] + "_" + taxa_dct["species"]

    return taxa_dct


def rdp_parse(s):
    """Parse RDP taxonomy string with 7 level format (SILVA uses it.)
    D_0__Bacteria;D_1__Epsilonbacteraeota;D_2__Campylobacteria;D_3__Campylobacterales;D_4__Thiovulaceae;D_5__Sulfuricurvum;D_6__Sulfuricurvum sp. EW1
    The ambiguous_taxa will be convert to empty string.
    """
    abbr_dct = {
        "D_0": "kingdom",
        "D_1": "phylum",
        "D_2": "class",
        "D_3": "order",
        "D_4": "family",
        "D_5": "genus",
        "D_6": "species",
    }
    taxa_dct = {
        "kingdom": "",
        "phylum": "",
        "class": "",
        "order": "",
        "family": "",
        "genus": "",
        "species": "",
    }
    tokens = s.split(";")
    for token in tokens:  # D_0__Bacteria, or Ambiguous_taxa
        if token == "Ambiguous_taxa":
            break
        taxLv, taxName = token.split("__")
        # Make the output behave like GG parse
        taxLv = abbr_dct[taxLv]
        taxa_dct[taxLv] = taxName

    return taxa_dct


def biom_to_pandas_df(biom_tab):
    """Will convert from biom Table object to pandas dataframe."""

    # Note this is based on James Morton's blog post:
    # http://mortonjt.blogspot.ca/2016/07/behind-scenes-with-biom-tables.html)
    return pd.DataFrame(
        np.array(biom_tab.matrix_data.todense()),
        index=biom_tab.ids(axis="observation"),
        columns=biom_tab.ids(axis="sample"),
    )


def read_seqabun(infile):
    """Will read in sequence abundance table in either TSV, BIOM, or mothur
    shared format."""

    # First check extension of input file. If extension is "biom" then read in
    # as BIOM table and return. This is expected to be the most common input.
    in_name, in_ext = os.splitext(infile)
    if in_ext == "biom":
        return biom_to_pandas_df(biom.load_table(infile))

    # Next check if input file is a mothur shared file or not by read in first
    # row only.
    mothur_format = False
    try:
        in_test = pd.read_table(filepath_or_buffer=infile, sep="\t", nrows=1)
        in_test_col = list(in_test.columns.values)
        if len(in_test_col) >= 4 and (
            in_test_col[0] == "label"
            and in_test_col[1] == "Group"
            and in_test_col[2] == "numOtus"
        ):
            mothur_format = True
    except Exception:
        pass

    # If identified to be mothur format then remove extra columns, set "Group"
    # to be index (i.e. row) names and then transpose.
    if mothur_format:
        input_seqabun = pd.read_table(filepath_or_buffer=infile, sep="\t")
        input_seqabun.drop(labels=["label", "numOtus"], axis=1, inplace=True)
        input_seqabun.set_index(
            keys="Group", drop=True, inplace=True, verify_integrity=True
        )
        input_seqabun.index.name = None
        return input_seqabun.transpose()
    else:
        return biom_to_pandas_df(biom.load_table(infile))
