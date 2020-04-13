from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import sys
import platform

import numpy as np  # type: ignore
from onnx import TensorProto
from onnx import mapping
from six import text_type, binary_type
from typing import Sequence, Any, Optional, Text, List

if platform.system() != 'AIX' and sys.byteorder != 'little':
    raise RuntimeError(
        'Numpy helper for tensor/ndarray is not available on big endian '
        'systems yet.')


def combine_pairs_to_complex(fa):  # type: (Sequence[int]) -> Sequence[np.complex64]
    return [complex(fa[i * 2], fa[i * 2 + 1]) for i in range(len(fa) // 2)]


def to_array(tensor):  # type: (TensorProto) -> np.ndarray[Any]
    """Converts a tensor def object to a numpy array.

    Inputs:
        tensor: a TensorProto object.
    Returns:
        arr: the converted array.
    """
    if tensor.HasField("segment"):
        raise ValueError(
            "Currently not supporting loading segments.")
    if tensor.data_type == TensorProto.UNDEFINED:
        raise TypeError("The element type in the input tensor is not defined.")

    tensor_dtype = tensor.data_type
    np_dtype = mapping.TENSOR_TYPE_TO_NP_TYPE[tensor_dtype]
    storage_type = mapping.TENSOR_TYPE_TO_STORAGE_TENSOR_TYPE[tensor_dtype]
    storage_np_dtype = mapping.TENSOR_TYPE_TO_NP_TYPE[storage_type]
    storage_field = mapping.STORAGE_TENSOR_TYPE_TO_FIELD[storage_type]
    dims = tensor.dims

    if tensor.data_type == TensorProto.STRING:
        utf8_strings = getattr(tensor, storage_field)
        ss = list(s.decode('utf-8') for s in utf8_strings)
        return np.asarray(ss).astype(np_dtype).reshape(dims)

    if tensor.HasField("raw_data"):
        # Raw_bytes support: using frombuffer.
        return np.frombuffer(
            tensor.raw_data,
            dtype=np_dtype).reshape(dims)
    else:
        data = getattr(tensor, storage_field),  # type: Sequence[np.complex64]
        if (tensor_dtype == TensorProto.COMPLEX64
                or tensor_dtype == TensorProto.COMPLEX128):
            data = combine_pairs_to_complex(data)
        return (
            np.asarray(
                data,
                dtype=storage_np_dtype)
            .astype(np_dtype)
            .reshape(dims)
        )


def from_array(arr, name=None):  # type: (np.ndarray[Any], Optional[Text]) -> TensorProto
    """Converts a numpy array to a tensor def.

    Inputs:
        arr: a numpy array.
        name: (optional) the name of the tensor.
    Returns:
        tensor_def: the converted tensor def.
    """
    tensor = TensorProto()
    tensor.dims.extend(arr.shape)
    if name:
        tensor.name = name

    if arr.dtype == np.object:
        # Special care for strings.
        tensor.data_type = mapping.NP_TYPE_TO_TENSOR_TYPE[arr.dtype]
        # TODO: Introduce full string support.
        # We flatten the array in case there are 2-D arrays are specified
        # We throw the error below if we have a 3-D array or some kind of other
        # object. If you want more complex shapes then follow the below instructions.
        # Unlike other types where the shape is automatically inferred from
        # nested arrays of values, the only reliable way now to feed strings
        # is to put them into a flat array then specify type astype(np.object)
        # (otherwise all strings may have different types depending on their length)
        # and then specify shape .reshape([x, y, z])
        flat_array = arr.flatten()
        for e in flat_array:
            if isinstance(e, text_type):
                tensor.string_data.append(e.encode('utf-8'))
            elif isinstance(e, np.ndarray):
                for s in e:
                    if isinstance(s, text_type):
                        tensor.string_data.append(s.encode('utf-8'))
            else:
                raise NotImplementedError(
                    "Unrecognized object in the object array, expect a string, or array of bytes: ", str(type(e)))
        return tensor

    # For numerical types, directly use numpy raw bytes.
    try:
        dtype = mapping.NP_TYPE_TO_TENSOR_TYPE[arr.dtype]
    except KeyError:
        raise RuntimeError(
            "Numpy data type not understood yet: {}".format(str(arr.dtype)))
    tensor.data_type = dtype
    tensor.raw_data = arr.tobytes()  # note: tobytes() is only after 1.9.

    return tensor


def to_array_from_sequence(sequence):  # type: (SequenceProto) -> np.ndarray[Any]
    """Converts a sequence def to a numpy array.

    Inputs:
        sequence: a SequenceProto object.
    Returns:
        arr: the converted array.
    """
    arr = np.array([])
    elem_type = sequence.elem_type
    if elem_type == TypeProto.Tensor or elem_type == TypeProto.SparseTensor:
        for elem in sequence.values:
            arr.append(to_array(elem))
    elif elem_type == TypeProto.Map:
        for elem in sequence.values:
            arr.append(to_dict_from_map(elem))
    elif elem_type == TypeProto.Sequence:
        for elem in sequence.values:
            arr.append(to_array_from_sequence(elem))
    else:
        raise TypeError("The element type in the input sequence is not defined.")
    return arr


def from_array_to_sequence(arr, name=None):  # type: type: (np.ndarray[Any], Optional[Text]) -> SequenceProto
    """Converts a numpy array into a sequence def.

    Inputs:
        arr: a numpy array.
    Returns:
        sequence: the converted sequence def.
    """
    sequence = SequenceProto()
    if name:
        sequence.name = name
    for elem in arr:
        # If elem is a tensor
        if elem.dtype == np.ndarray:
            sequence.values.append(from_array(elem))
        else:
            raise TypeError("The element type in the input sequence is not supported yet.")
    return sequence


def to_dict_from_map(map):  # type: (MapProto) -> np.ndarray[Any]
    """Converts a map def to a Python dictionary.

    Inputs:
        map: a MapProto object.
    Returns:
        dict: the converted dictionary.
    """
    dict = {}
    for kv_pair in map.pairs:
        key_type = kv_pair.key_type
        value_type = kv_pair.value_type
        key_field = mapping.STORAGE_MAP_KEY_TYPE_TO_FIELD[key_type]
        key = get_attr(kv_pair, key_field)
        value = kv_pair.value
        if value_type == TypeProto.Tensor or value_type == TypeProto.SparseTensor:
            dict[key] = to_array(value)
        elif value_type == TypeProto.Map:
            dict[key] = to_dict_from_map(value)
        elif elem_type == TypeProto.Sequence:
            dict[key] = to_array_from_sequence(value)
        else:
            raise TypeError("The value type in the Map is not defined.")
    return dict
