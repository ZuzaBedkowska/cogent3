from collections import defaultdict, namedtuple
from numpy import log, zeros, float64, int32, array, sqrt, dot, diag, eye
from numpy.linalg import det, norm, inv, LinAlgError

from cogent3 import DNA, RNA, LoadTable, get_moltype
from cogent3.util.progress_display import display_wrap
from cogent3.util.dict_array import DictArray

__author__ = "Gavin Huttley, Yicheng Zhu and Ben Kaehler"
__copyright__ = "Copyright 2007-2016, The Cogent Project"
__credits__ = ["Gavin Huttley", "Yicheng Zhu", "Ben Kaehler"]
__license__ = "GPL"
__version__ = "3.0a2"
__maintainer__ = "Gavin Huttley"
__email__ = "gavin.huttley@anu.edu.au"
__status__ = "Alpha"  # pending addition of protein distance metrics


def _same_moltype(ref, query):
    """if ref and query have the same states"""
    return set(ref) == set(query)


def get_pyrimidine_indices(moltype):
    """returns pyrimidine indices for the moltype"""
    states = list(moltype)
    if _same_moltype(RNA, moltype):
        return list(map(states.index, 'CU'))
    elif _same_moltype(DNA, moltype):
        return list(map(states.index, 'CT'))
    else:
        raise RuntimeError('Non-nucleic acid MolType')


def get_purine_indices(moltype):
    """returns purine indices for the moltype"""
    states = list(moltype)
    if not _same_moltype(RNA, moltype) and not _same_moltype(DNA, moltype):
        raise RuntimeError('Non-nucleic acid MolType')

    return list(map(states.index, 'AG'))


def get_matrix_diff_coords(indices):
    """returns coordinates for off diagonal elements"""
    return [(i, j) for i in indices for j in indices if i != j]


def get_moltype_index_array(moltype, invalid=-9):
    """returns the index array for a molecular type"""
    canonical_chars = list(moltype)
    # maximum ordinal for an allowed character, this defines the length of
    # the required numpy array
    max_ord = max(list(map(ord, list(moltype.All.keys()))))
    char_to_index = zeros(max_ord + 1, int32)
    # all non canonical_chars are ``invalid''
    char_to_index.fill(invalid)

    for i in range(len(canonical_chars)):
        c = canonical_chars[i]
        o = ord(c)
        char_to_index[o] = i

    return char_to_index


def seq_to_indices(seq, char_to_index):
    """returns an array with sequence characters replaced by their index"""
    ords = list(map(ord, seq))
    indices = char_to_index.take(ords)
    return indices


def _fill_diversity_matrix(matrix, seq1, seq2):
    """fills the diversity matrix for valid positions.

    Assumes the provided sequences have been converted to indices with
    invalid characters being negative numbers (use get_moltype_index_array
    plus seq_to_indices)."""
    paired = array([seq1, seq2]).T
    paired = paired[paired.min(axis=1) >= 0]
    for i in range(len(paired)):
        matrix[paired[i][0], paired[i][1]] += 1


def _hamming(matrix):
    """computes the edit distance
    Parameters
    ----------
    matrix : array
        2D numpy array of counts
    Returns
    -------
    total of the matrix, the proportion of changes, hamming distance, variance
    (the variance calculation is not yet implemented)
    """
    # todo implement the estimate of the variance
    invalid = None, None, None, None
    total = matrix.sum()
    dist = total - diag(matrix).sum()
    if total == 0:
        return invalid

    p = dist / total

    return total, p, dist, None


def _jc69_from_matrix(matrix):
    """computes JC69 stats from a diversity matrix"""
    invalid = None, None, None, None
    total = matrix.sum()
    diffs = total - diag(matrix).sum()
    if total == 0:
        return invalid

    p = diffs / total
    if p >= 0.75:  # cannot take log
        return invalid

    factor = (1 - (4 / 3) * p)

    dist = -3.0 * log(factor) / 4
    var = p * (1 - p) / (factor * factor * total)
    return total, p, dist, var


def _tn93_from_matrix(matrix, freqs, pur_indices, pyr_indices, pur_coords,
                      pyr_coords, tv_coords):
    invalid = None, None, None, None

    total = matrix.sum()
    freqs = matrix.sum(axis=0) + matrix.sum(axis=1)
    freqs /= (2 * total)

    if total == 0:
        return invalid

    p = matrix.take(pur_coords + pyr_coords + tv_coords).sum() / total

    freq_purs = freqs.take(pur_indices).sum()
    prod_purs = freqs.take(pur_indices).prod()
    freq_pyrs = freqs.take(pyr_indices).sum()
    prod_pyrs = freqs.take(pyr_indices).prod()

    # purine transition diffs
    pur_ts_diffs = matrix.take(pur_coords).sum()
    pur_ts_diffs /= total
    # pyr transition  diffs
    pyr_ts_diffs = matrix.take(pyr_coords).sum()
    pyr_ts_diffs /= total
    # transversions
    tv_diffs = matrix.take(tv_coords).sum() / total

    coeff1 = 2 * prod_purs / freq_purs
    coeff2 = 2 * prod_pyrs / freq_pyrs
    coeff3 = 2 * (freq_purs * freq_pyrs -
                  (prod_purs * freq_pyrs / freq_purs) -
                  (prod_pyrs * freq_purs / freq_pyrs))

    term1 = 1 - pur_ts_diffs / coeff1 - tv_diffs / (2 * freq_purs)
    term2 = 1 - pyr_ts_diffs / coeff2 - tv_diffs / (2 * freq_pyrs)
    term3 = 1 - tv_diffs / (2 * freq_purs * freq_pyrs)

    if term1 <= 0 or term2 <= 0 or term3 <= 0:  # log will fail
        return invalid

    dist = -coeff1 * log(term1) - coeff2 * log(term2) - coeff3 * log(term3)
    v1 = 1 / term1
    v2 = 1 / term2
    v3 = 1 / term3
    v4 = (coeff1 * v1 / (2 * freq_purs)) + \
         (coeff2 * v2 / (2 * freq_pyrs)) + \
         (coeff3 * v3 / (2 * freq_purs * freq_pyrs))
    var = v1 ** 2 * pur_ts_diffs + v2 ** 2 * pyr_ts_diffs + v4 ** 2 * tv_diffs - \
        (v1 * pur_ts_diffs + v2 * pyr_ts_diffs + v4 * tv_diffs) ** 2
    var /= total

    return total, p, dist, var


def _logdetcommon(matrix):
    invalid = (None,) * 5

    total = matrix.sum()
    diffs = total - matrix.diagonal().sum()
    if total == 0:
        return invalid

    p = diffs / total

    if diffs == 0:  # seqs indentical
        return invalid

    # we replace the missing diagonal states with a frequency of 0.5,
    # then normalise
    frequency = matrix.copy()
    frequency[(frequency == 0) * eye(*matrix.shape, dtype=bool)] = 0.5
    frequency /= frequency.sum()

    if det(frequency) <= 0:  # if the result is nan
        return invalid

    # the inverse matrix of frequency, every element is squared
    M_matrix = inv(frequency) ** 2
    freqs = [frequency.sum(axis=axis) for axis in (0, 1)]
    var_term = dot(M_matrix, frequency).diagonal().sum()

    return total, p, frequency, freqs, var_term


def _paralinear(matrix):
    """the paralinear distance from a diversity matrix"""

    invalid = (None,) * 4

    total, p, frequency, freqs, var_term = _logdetcommon(matrix)
    if frequency is None:
        return invalid

    r = matrix.shape[0]
    d_xy = - log(det(frequency) / sqrt((freqs[0] * freqs[1]).prod())) / r
    var = (var_term - (1 / sqrt(freqs[0] * freqs[1])).sum()) / (r ** 2 * total)

    return total, p, d_xy, var


def _logdet(matrix, use_tk_adjustment=True):
    """returns the LogDet from a diversity matrix
    Arguments:
        - use_tk_adjustment: when True, unequal state frequencies are allowed
    """

    invalid = (None,) * 4

    total, p, frequency, freqs, var_term = _logdetcommon(matrix)
    if frequency is None:
        return invalid

    r = matrix.shape[0]
    if use_tk_adjustment:
        coeff = (sum(sum(freqs) ** 2) / 4 - 1) / (r - 1)
        d_xy = coeff * log(det(frequency) /
                           sqrt((freqs[0] * freqs[1]).prod()))
        var = None
    else:
        d_xy = - log(det(frequency)) / r - log(r)
        var = (var_term / r ** 2 - 1) / total

    return total, p, d_xy, var


try:
    from ._pairwise_distance import \
        _fill_diversity_matrix as fill_diversity_matrix
    # raise ImportError # for testing
except ImportError:
    fill_diversity_matrix = _fill_diversity_matrix


def _number_formatter(template):
    """flexible number formatter"""

    def call(val):
        try:
            result = template % val
        except TypeError:
            result = val
        return result

    return call


def _make_stat_table(stats, names, **kwargs):
    header = [r'Seq1 \ Seq2'] + names
    rows = zeros((len(names), len(names)), dtype="O")
    for i in range(len(names) - 1):
        n1 = names[i]
        for j in range(i + 1, len(names)):
            n2 = names[j]
            val = stats[(n1, n2)]
            rows[i, j] = val
            rows[j, i] = val
    rows = rows.tolist()
    for i in range(len(names)):
        rows[i].insert(0, names[i])

    table = LoadTable(header=header, rows=rows, row_ids=True,
                      missing_data='*', **kwargs)
    return table


class _PairwiseDistance(object):
    """base class for computing pairwise distances"""
    valid_moltypes = ()

    def __init__(self, moltype, invalid=-9, alignment=None):
        super(_PairwiseDistance, self).__init__()
        moltype = get_moltype(moltype)
        if moltype.label not in self.valid_moltypes:
            name = self.__class__.__name__
            msg = (f"Invalid moltype for {name}: '{moltype.label}' not "
                   f"in {self.valid_moltypes}")
            raise ValueError(msg)

        self.moltype = moltype
        self.char_to_indices = get_moltype_index_array(moltype, invalid=invalid)
        self._dim = len(list(moltype))
        self._dists = None
        self._dupes = None
        self._duped = None

        self.names = None
        self.indexed_seqs = None

        if alignment is not None:
            self._convert_seqs_to_indices(alignment)

        self._func_args = []

    def _convert_seqs_to_indices(self, alignment):
        assert isinstance(alignment.moltype, type(self.moltype)), \
            'Alignment does not have correct MolType'

        self._dists = {}
        self.names = alignment.names[:]
        indexed_seqs = []
        for name in self.names:
            seq = alignment.get_gapped_seq(name)
            indexed = seq_to_indices(str(seq), self.char_to_indices)
            indexed_seqs.append(indexed)

        self.indexed_seqs = array(indexed_seqs)

    @property
    def duplicated(self):
        """returns mapping of IDs to duplicates as {id:[dupe1, ..], },
        or None"""
        return self._duped

    @staticmethod
    def func():
        pass  # over ride in subclasses

    @display_wrap
    def run(self, alignment=None, ui=None):
        """computes the pairwise distances"""
        self._dupes = None
        self._duped = None

        dupes = set()
        duped = defaultdict(list)
        Stats = namedtuple("Stats",
                           ["length", "fraction_variable", "dist", "variance"])

        if alignment is not None:
            self._convert_seqs_to_indices(alignment)

        names = self.names[:]
        matrix = zeros((self._dim, self._dim), float64)
        off_diag = [(i, j) for i in range(self._dim)
                    for j in range(self._dim) if i != j]
        off_diag = tuple([tuple(a) for a in zip(*off_diag)])

        done = 0.0
        to_do = (len(names) * len(names) - 1) / 2
        for i in range(len(names) - 1):
            if i in dupes:
                continue

            name_1 = names[i]
            s1 = self.indexed_seqs[i]
            for j in range(i + 1, len(names)):
                if j in dupes:
                    continue

                name_2 = names[j]
                ui.display('%s vs %s' % (name_1, name_2), done / to_do)
                done += 1
                matrix.fill(0)
                s2 = self.indexed_seqs[j]
                fill_diversity_matrix(matrix, s1, s2)
                if not (matrix[off_diag] > 0).any():
                    # j is a duplicate of i
                    dupes.update([j])
                    duped[i].append(j)
                    continue

                total, p, dist, var = self.func(matrix, *self._func_args)
                result = Stats(total, p, dist, var)
                self._dists[(name_1, name_2)] = result
                self._dists[(name_2, name_1)] = result

        self._dupes = [names[i] for i in dupes] or None
        if duped:
            self._duped = {}
            for k, v in duped.items():
                key = names[k]
                vals = [names[i] for i in v]
                self._duped[key] = vals

            # clean the distances so only unique seqs included
            remove = set(self._dupes)
            keys = list(self._dists.keys())
            for key in keys:
                if set(key) & remove:
                    del (self._dists[key])

    __call__ = run

    def get_pairwise_distances(self, include_duplicates=True):
        """returns a matrix of pairwise distances.

        Arguments:
        - include_duplicates: all seqs included in the distances,
          otherwise only unique sequences are included.
        """
        if self._dists is None:
            return None

        dists = {k: self._dists[k].dist for k in self._dists}
        if include_duplicates:
            dists = self._expand(dists)

        result = DistanceMatrix(dists)
        return result

    def _expand(self, pwise):
        """returns a pwise statistic dict that includes duplicates"""
        if not self.duplicated:
            # no duplicates, nothing to do
            return pwise

        redundants = {}
        for k in self.duplicated:
            for r in self.duplicated[k]:
                redundants[r] = k

        names = self.names[:]
        for add, alias in redundants.items():
            for name in names:
                if name == add:
                    continue
                if name == alias:
                    val = 0
                else:
                    val = pwise.get((alias, name), None)
                pwise[(add, name)] = pwise[(name, add)] = val

        return pwise

    @property
    def dists(self):
        if self._dists is None:
            return None

        stats = {k: self._dists[k].dist for k in self._dists}
        stats = self._expand(stats)
        kwargs = dict(title='Pairwise Distances', digits=4)
        t = _make_stat_table(stats, self.names, **kwargs)
        return t

    @property
    def stderr(self):
        if self._dists is None:
            return None

        stats = {k: sqrt(self._dists[k].variance) for k in self._dists}
        stats = self._expand(stats)
        kwargs = dict(title='Standard Error of Pairwise Distances', digits=4)
        t = _make_stat_table(stats, self.names, **kwargs)
        return t

    @property
    def variances(self):
        if self._dists is None:
            return None

        stats = {k: self._dists[k].variance for k in self._dists}
        stats = self._expand(stats)
        kwargs = dict(title='Variances of Pairwise Distances', digits=4)
        t = _make_stat_table(stats, self.names, **kwargs)
        var_formatter = _number_formatter("%.2e")
        for name in self.names:
            t.format_column(name, var_formatter)
        return t

    @property
    def proportions(self):
        if self._dists is None:
            return None

        stats = {k: self._dists[k].fraction_variable for k in self._dists}
        stats = self._expand(stats)
        kwargs = dict(title='Proportion variable sites', digits=4)
        t = _make_stat_table(stats, self.names, **kwargs)
        return t

    @property
    def lengths(self):
        if self._dists is None:
            return None

        stats = {k: self._dists[k].length for k in self._dists}
        stats = self._expand(stats)
        kwargs = dict(title='Pairwise Aligned Lengths', digits=0)
        t = _make_stat_table(stats, self.names, **kwargs)
        return t


class HammingPair(_PairwiseDistance):
    """Hamming distance calculator for pairwise alignments"""
    valid_moltypes = ('dna', 'rna', 'protein', 'text')

    def __init__(self, moltype='text', *args, **kwargs):
        """states: the valid sequence states"""
        super(HammingPair, self).__init__(moltype, *args, **kwargs)
        self.func = _hamming


class _NucleicSeqPair(_PairwiseDistance):
    """base class pairwise distance calculator for nucleic acid seqs"""
    valid_moltypes = ('dna', 'rna')

    def __init__(self, moltype='dna', *args, **kwargs):
        super(_NucleicSeqPair, self).__init__(moltype, *args, **kwargs)
        if not _same_moltype(DNA, self.moltype) and \
                not _same_moltype(RNA, self.moltype):
            raise RuntimeError('Invalid MolType for this metric')


class JC69Pair(_NucleicSeqPair):
    """JC69 distance calculator for pairwise alignments"""

    def __init__(self, moltype='dna', *args, **kwargs):
        """states: the valid sequence states"""
        super(JC69Pair, self).__init__(moltype, *args, **kwargs)
        self.func = _jc69_from_matrix


class TN93Pair(_NucleicSeqPair):
    """TN93 calculator for pairwise alignments"""

    def __init__(self, moltype='dna', *args, **kwargs):
        """states: the valid sequence states"""
        super(TN93Pair, self).__init__(moltype, *args, **kwargs)
        self._freqs = zeros(self._dim, float64)
        self.pur_indices = get_purine_indices(self.moltype)
        self.pyr_indices = get_pyrimidine_indices(self.moltype)

        # matrix coordinates
        self.pyr_coords = get_matrix_diff_coords(self.pyr_indices)
        self.pur_coords = get_matrix_diff_coords(self.pur_indices)

        self.tv_coords = get_matrix_diff_coords(list(range(self._dim)))
        for coord in self.pur_coords + self.pyr_coords:
            self.tv_coords.remove(coord)

        # flattened
        self.pyr_coords = [i * 4 + j for i, j in self.pyr_coords]
        self.pur_coords = [i * 4 + j for i, j in self.pur_coords]
        self.tv_coords = [i * 4 + j for i, j in self.tv_coords]

        self.func = _tn93_from_matrix
        self._func_args = [self._freqs, self.pur_indices,
                           self.pyr_indices, self.pur_coords,
                           self.pyr_coords, self.tv_coords]


class LogDetPair(_PairwiseDistance):
    """computes logdet distance between sequence pairs"""
    valid_moltypes = ('dna', 'rna', 'protein')

    def __init__(self, moltype='dna', use_tk_adjustment=True, *args, **kwargs):
        """Arguments:
            - moltype: string or moltype instance (must be dna or rna)
            - use_tk_adjustment: use the correction of Tamura and Kumar 2002
        """
        super(LogDetPair, self).__init__(moltype, *args, **kwargs)
        self.func = _logdet
        self._func_args = [use_tk_adjustment]

    def run(self, use_tk_adjustment=None, *args, **kwargs):
        if use_tk_adjustment is not None:
            self._func_args = [use_tk_adjustment]

        super(LogDetPair, self).run(*args, **kwargs)


class ParalinearPair(_PairwiseDistance):
    """computes the paralinear distance (Lake 1994) between sequence pairs"""
    valid_moltypes = ('dna', 'rna', 'protein')

    def __init__(self, moltype='dna', *args, **kwargs):
        super(ParalinearPair, self).__init__(moltype, *args, **kwargs)
        self.func = _paralinear


_calculators = {'paralinear': ParalinearPair,
                'logdet': LogDetPair,
                'jc69': JC69Pair,
                'tn93': TN93Pair,
                'hamming': HammingPair}


def get_calculator(name, *args, **kwargs):
    """returns a pairwise distance calculator

    name is converted to lower case"""
    name = name.lower()
    if name not in _calculators:
        raise ValueError('Unknown pairwise distance calculator "%s"' % name)

    calc = _calculators[name]
    return calc(*args, **kwargs)


def available_distances():
    """returns Table listing available pairwise genetic distance calculator
    Notes
    -----
    For more complicated genetic distance methods, see the evolve.models module.
    """
    from cogent3 import LoadTable
    rows = []
    for n, c in _calculators.items():
        rows.append([n, ', '.join(c.valid_moltypes)])

    table = LoadTable(header=['Abbreviation', 'Suitable for moltype'],
                      rows=rows,
                      title=("Specify a pairwise genetic distance calculator "
                             "using 'Abbreviation' (case insensitive)."),
                      row_ids=True)
    return table


class DistanceMatrix(DictArray):
    """pairwise distance matrix"""

    def __init__(self, dists, invalid=None):
        super(DistanceMatrix, self).__init__(dists, dtype='O')
        self._invalid = invalid

    def __setitem__(self, names, value):
        (index, remaining) = self.template.interpret_index(names)
        self.array[index] = value
        return

    def todict(self):
        result = {}
        for n1 in self.template.names[0]:
            for n2 in self.template.names[1]:
                if n1 == n2:
                    continue
                result[(n1, n2)] = self[n1, n2]
        return result

    def drop_invalid(self, invalid=None):
        """drops all rows / columns with an invalid entry"""
        if (self.shape[0] != self.shape[1] or
                self.template.names[0] != self.template.names[0]):
            raise RuntimeError('Must be a square matrix')
        names = array(self.template.names[0])
        cols = (self.array == invalid).sum(axis=0)
        exclude = names[cols != 0].tolist()
        rows = (self.array == invalid).sum(axis=1)
        exclude += names[rows != 0].tolist()
        exclude = set(exclude)
        keep = [i for i, n in enumerate(names) if n not in exclude]
        data = self.array.take(keep, axis=0)
        data = data.take(keep, axis=1)
        names = names.take(keep)
        dists = {(names[i], names[j]): data[i, j]
                 for i in range(len(names))
                 for j in range(len(names)) if i != j}
        if not dists:
            result = None
        else:
            result = self.__class__(dists)
        return result

    def build_tree(self, show_progress=False):
        """returns a neighbour joining tree
        Returns
        -------
        an estimated Neighbour Joining Tree, note that invalid distances are dropped
        prior to building the tree
        """
        from cogent3.phylo.nj import gnj
        dists = self.drop_invalid()
        if not dists or dists.shape[0] == 1:
            raise ValueError('Too few distances to build a tree')
        dists = dists.todict(flatten=True)
        return gnj(dists, show_progress=show_progress)
