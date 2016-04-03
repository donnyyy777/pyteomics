"""
mzml - reader for mass spectrometry data in mzML format
=======================================================

Summary
-------

mzML is a standard rich XML-format for raw mass spectrometry data storage.
Please refer to http://www.psidev.info/index.php?q=node/257 for the detailed
specification of the format and the structure of mzML files.

This module provides a minimalistic way to extract information from mzIdentML
files. You can use the old functional interface (:py:func:`read`) or the new
object-oriented interface (:py:class:`MzML`) to iterate over entries in
``<spectrum>`` elements.

Data access
-----------

  :py:class:`MzML` - a class representing a single mzML file.
  Other data access functions use this class internally.

  :py:func:`read` - iterate through spectra in mzML file. Data from a
  single spectrum are converted to a human-readable dict. Spectra themselves are
  stored under 'm/z array' and 'intensity array' keys.

  :py:func:`chain` - read multiple mzML files at once.

  :py:func:`chain.from_iterable` - read multiple files at once, using an
  iterable of files.

Deprecated functions
--------------------

  :py:func:`version_info` - get version information about the mzML file.
  You can just read the corresponding attribute of the :py:class:`MzML` object.

  :py:func:`iterfind` - iterate over elements in an mzML file.
  You can just call the corresponding method of the :py:class:`MzML` object.

Dependencies
------------

This module requires :py:mod:`lxml` and :py:mod:`numpy`.

-------------------------------------------------------------------------------
"""

#   Copyright 2012 Anton Goloborodko, Lev Levitsky
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import numpy as np
import zlib
import base64
import re
from . import xml, auxiliary as aux
from .xml import etree





def _decode_base64_data_array(source, dtype, is_compressed):
    """Read a base64-encoded binary array.

    Parameters
    ----------
    source : str
        A binary array encoded with base64.
    dtype : str
        The type of the array in numpy dtype notation.
    is_compressed : bool
        If True then the array will be decompressed with zlib.

    Returns
    -------
    out : numpy.array
    """

    decoded_source = base64.b64decode(source.encode('ascii'))
    if is_compressed:
        decoded_source = zlib.decompress(decoded_source)
    output = np.frombuffer(decoded_source, dtype=dtype)
    return output

class MzML(xml.XML):
    """Parser class for mzML files."""
    file_format = 'mzML'
    _root_element = 'mzML'
    _default_schema = xml._mzml_schema_defaults
    _default_version = '1.1.0'
    _default_iter_tag = 'spectrum'
    _structures_to_flatten = {'binaryDataArrayList'}

    def _get_info_smart(self, element, **kw):
        name = xml._local_name(element)
        kwargs = dict(kw)
        rec = kwargs.pop('recursive', None)
        if name in {'indexedmzML', 'mzML'}:
            info =  self._get_info(element,
                    recursive=(rec if rec is not None else False),
                    **kwargs)
        else:
            info = self._get_info(element,
                    recursive=(rec if rec is not None else True),
                    **kwargs)
        if 'binary' in info:
            types = {'32-bit float': 'f', '64-bit float': 'd'}
            for t, code in types.items():
                if t in info:
                    dtype = code
                    del info[t]
                    break
            # sometimes it's under 'name'
            else:
                if 'name' in info:
                    for t, code in types.items():
                        if t in info['name']:
                            dtype = code
                            info['name'].remove(t)
                            break
            compressed = True
            if 'zlib compression' in info:
                del info['zlib compression']
            elif 'name' in info and 'zlib compression' in info['name']:
                info['name'].remove('zlib compression')
            else:
                compressed = False
                info.pop('no compression', None)
                try:
                    info['name'].remove('no compression')
                    if not info['name']: del info['name']
                except (KeyError, TypeError):
                    pass
            b = info.pop('binary')
            if b:
                array = _decode_base64_data_array(
                                b, dtype, compressed)
            else:
                array = np.array([], dtype=dtype)
            for k in info:
                if k.endswith(' array') and not info[k]:
                    info = {k: array}
                    break
            else:
                found = False
                # workaround for https://bitbucket.org/levitsky/pyteomics/issues/11
                if isinstance(info.get('name'), list):
                    knames = info['name']
                    for val in knames:
                        if val.endswith(' array'):
                            info = {val: array}
                            found = True
                            break
                # last fallback
                if not found:
                    info['binary'] = array
        if 'binaryDataArray' in info:
            for array in info.pop('binaryDataArray'):
                info.update(array)
        intkeys = {'ms level'}
        for k in intkeys:
            if k in info:
                info[k] = int(info[k])
        return info

def read(source, read_schema=True, iterative=True):
    """Parse `source` and iterate through spectra.

    Parameters
    ----------
    source : str or file
        A path to a target mzML file or the file object itself.

    read_schema : bool, optional
        If :py:const:`True`, attempt to extract information from the XML schema
        mentioned in the mzML header (default). Otherwise, use default
        parameters. Disable this to avoid waiting on long network connections or
        if you don't like to get the related warnings.

    iterative : bool, optional
        Defines whether iterative parsing should be used. It helps reduce
        memory usage at almost the same parsing speed. Default is
        :py:const:`True`.

    Returns
    -------
    out : iterator
       An iterator over the dicts with spectra properties.
    """

    return MzML(source, read_schema=read_schema, iterative=iterative)

def iterfind(source, path, **kwargs):
    """Parse `source` and yield info on elements with specified local
    name or by specified "XPath".

    .. note:: This function is provided for backward compatibility only.
        If you do multiple :py:func:`iterfind` calls on one file, you should
        create an :py:class:`MzML` object and use its
        :py:meth:`!iterfind` method.

    Parameters
    ----------
    source : str or file
        File name or file-like object.

    path : str
        Element name or XPath-like expression. Only local names separated
        with slashes are accepted. An asterisk (`*`) means any element.
        You can specify a single condition in the end, such as:
        ``"/path/to/element[some_value>1.5]"``
        Note: you can do much more powerful filtering using plain Python.
        The path can be absolute or "free". Please don't specify
        namespaces.

    recursive : bool, optional
        If :py:const:`False`, subelements will not be processed when
        extracting info from elements. Default is :py:const:`True`.

    iterative : bool, optional
        Specifies whether iterative XML parsing should be used. Iterative
        parsing significantly reduces memory usage and may be just a little
        slower. When `retrieve_refs` is :py:const:`True`, however, it is
        highly recommended to disable iterative parsing if possible.
        Default value is :py:const:`True`.

    read_schema : bool, optional
        If :py:const:`True`, attempt to extract information from the XML schema
        mentioned in the mzIdentML header (default). Otherwise, use default
        parameters. Disable this to avoid waiting on long network connections or
        if you don't like to get the related warnings.

    Returns
    -------
    out : iterator
    """
    return MzML(source, **kwargs).iterfind(path, **kwargs)

version_info = xml._make_version_info(MzML)

chain = aux._make_chain(read, 'read')


def read_from_start(obj):
    """
    Given an object, try to get a reader for it that is located
    at the start of the file. If given an actual file object, this function
    will seek to the start of the file.

    Parameters
    ----------
    obj : str or file-like
        The object to acquire a reader on

    Returns
    -------
    file
    """
    if hasattr(obj, 'closed'):
        if obj.closed:
            obj = open(obj.name)
        obj.seek(0)
        return obj
    else:
        return open(obj)


def find_index_list_offset(file_obj):
    """
    Search relative to the bottom of the file upwards to find the offsets
    of the index lists.

    Parameters
    ----------
    file_obj : str or file-like
        File to search. Opened with :func:`read_from_start`

    Returns
    -------
    list of int
        A list of byte offsets for `<indexList>` elements
    """
    f = read_from_start(file_obj)
    f.seek(-1024, 2)
    text = f.read(1024)
    index_offsets = list(map(int, re.findall(r"<indexListOffset>(\d+)</indexListOffset>", text)))
    f.close()
    return index_offsets


def find_index_list(file_obj):
    """
    Extract lists of index offsets from the end of the file.

    Parameters
    ----------
    file_obj : str or file-like
        File to extract indices from. Opened with :func:`read_from_start`

    Returns
    -------
    dict of str -> dict of str -> int
    """
    offsets = find_index_list_offset(file_obj)
    index_list = {}
    name_pattern = re.compile(r"<index name=\"(\S+)\">")
    offset_pattern = re.compile(r"<offset idRef=\"([^\"]+)\">(\d+)</offset>")
    end_pattern = re.compile(r"</index>")
    for offset in offsets:
        # Sometimes the offset is at the very beginning of the file,
        # due to a bug in an older version of ProteoWizard. If this crude
        # check fails, don't bother searching the entire file, and fall back
        # on the base class's mechanisms.
        #
        # Alternative behavior here would be to start searching for the start
        # of the index from the bottom of the file, but this version of Proteowizard
        # also emits invalid offsets which do not improve retrieval time.
        if offset < 1024:
            continue
        f = read_from_start(file_obj)
        f.seek(offset)
        index_offsets = {}
        index_name = None
        for line in f:
            # print line
            match = name_pattern.search(line)
            if match:
                index_name = match.groups()[0]
                continue
            match = offset_pattern.search(line)
            if match:
                id_ref, offset = match.groups()
                offset = int(offset)
                index_offsets[id_ref] = offset
                continue
            match = end_pattern.search(line)
            if match:
                index_list[index_name] = index_offsets
                index_offsets = {}
    return index_list


class IndexedMzML(MzML):
    def __init__(self, *args, **kwargs):
        super(IndexedMzML, self).__init__(*args, **kwargs)
        self._offset_index = None
        self.reset()
        self._build_index()
        self.reset()

    def _build_index(self):
        """
        Build up a `dict` of `dict` of offsets for elements. Calls :func:`find_index_list`
        on :attr:`_source` and assigns the return value to :attr:`_offset_index`
        """
        self._offset_index = find_index_list(self._source)

    def _find_by_id_no_reset(self, elem_id):
        """
        An almost exact copy of :meth:`get_by_id` with the difference that it does
        not reset the file reader's position before iterative parsing.

        Parameters
        ----------
        elem_id : str
            The element id to query for

        Returns
        -------
        lxml.Element
        """
        found = False
        for event, elem in etree.iterparse(self._source, events=('start', 'end'), remove_comments=True):
            if event == 'start':
                if elem.attrib.get("id") == elem_id:
                    found = True
            else:
                if elem.attrib.get("id") == elem_id:
                    return elem
                if not found:
                    elem.clear()

    def get_by_id(self, elem_id):
        """
        Retrieve the requested entity by its id. If the entity
        is a spectrum described in the offset index, it will be retrieved
        by immediately seeking to the starting position of the entry, otherwise
        falling back to parsing from the start of the file.

        Parameters
        ----------
        elem_id : str
            The id value of the entity to retrieve.

        Returns
        -------
        dict
        """
        try:
            index = self._offset_index['spectrum']
            offset = index[elem_id]
            self._source.seek(offset)
            elem = self._find_by_id_no_reset(elem_id)
            data = self._get_info_smart(elem, recursive=True)
            return data
        except KeyError:
            return super(IndexedMzML, self).get_by_id(elem_id)

    def __getitem__(self, elem_id):
        return self.get_by_id(elem_id)

    def __iter__(self):
        try:
            index = self._offset_index['spectrum'].items()
            items = sorted(index, key=lambda x: x[1])
            for scan_id, offset in items:
                yield self.get_by_id(scan_id)
        except KeyError:
            for scan in self.iterfind('spectrum'):
                yield scan
