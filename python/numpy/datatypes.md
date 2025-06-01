# Типы данных Numpy 

[basics types](https://numpy.org/doc/stable/user/basics.types.html)


```python
a = np.array([1, 2, 5000, 1000], dtype='int8')
```

Типы данных которые поддерживает пакет NumPy.

```python
np.sctypeDict
```

`void` <class 'numpy.void'>, # [numpy.void](./datatypes_void.md)
 
`bool` <class 'numpy.bool'>, 
`bool_` <class 'numpy.bool'>,  # Логический тип (истина или ложь), хранящийся в виде байта.  
 
`str` <class 'numpy.str_'>, 
`str_` <class 'numpy.str_'>, # Для представления строк.
`unicode` <class 'numpy.str_'>, 
 
`int8` <class 'numpy.int8'>,   # Целые числа в диапазоне от -128 по 127 (числа размером 1 байт).
`byte` <class 'numpy.int8'>,  
`uint8` <class 'numpy.uint8'>, # Целые числа в диапазоне от 0 по 255 (числа размером 1 байт).  
`ubyte` <class 'numpy.uint8'>, 
 
`int16` <class 'numpy.int16'>, # Целые числа в диапазоне от -32768 по 32767, (числа размером 2 байта).  
`short` <class 'numpy.int16'>, 
`uint16` <class 'numpy.uint16'>, # Целые числа в диапазоне от 0 по 65535 (числа размером 2 байта).  
`ushort` <class 'numpy.uint16'>, 


`int32` <class 'numpy.int32'>,  # Целые числа в диапазоне от -2147483648 по 2147483647, (числа размером 4 байта).
`intc` <class 'numpy.int32'>, # Идентичен C int (int32 или int64).  
`uint32` <class 'numpy.uint32'>, # Целые числа в диапазоне от 0 по 4294967295 (числа размером 4 байта).
`uintc` <class 'numpy.uint32'>, 
 
`int64` <class 'numpy.int64'>,  # Целые числа размером 8 байт.
`long` <class 'numpy.int64'>, 
`uint64` <class 'numpy.uint64'>, # Целые беззнаковыечисла размером 8 байт.  
`ulong` <class 'numpy.uint64'>, 
`intp` <class 'numpy.int64'>, # Целочисленный тип, используемый для индексирования (такой же, как C ssize_t, как правило это либо int64 либо int32).
`uintp` <class 'numpy.uint64'>,
`int_` <class 'numpy.int64'>, # Целочисленный тип установленный по умолчанию (такой же, как C long, как правило это либо int64 либо int32).  
`int` <class 'numpy.int64'>, 
`uint` <class 'numpy.uint64'>, 
 
`float16` <class 'numpy.float16'>, # Вещественные числа половинной точности: 1 бит знака, 5 бит экспоненты, 10 бит мантисы (числа размером 2 байта).
`half` <class 'numpy.float16'>,
  
`float32` <class 'numpy.float32'>, # Вещественные числа одинарной точности: 1 бит знака, 8 бит экспоненты, 23 бита мантисы (числа размером 4 байта).
`single` <class 'numpy.float32'>,
  
`float64` <class 'numpy.float64'>, # Вещественные числа двойной точности: 1 бит знака, 11 бит экспоненты, 52 бита мантисы (числа размером 8 байт).
`double` <class 'numpy.float64'>, 
`float` <class 'numpy.float64'>,
 
`float128` <class 'numpy.longdouble'>, 
`longdouble` <class 'numpy.longdouble'>,

`csingle` <class 'numpy.complex64'>,
`complex64` <class 'numpy.complex64'>, #  Комплексные числа, в которых действительная и мнимая части представлены двумя вещественными числами типа float32.
  
`complex` <class 'numpy.complex128'>,
`cdouble` <class 'numpy.complex128'>,
`complex128` <class 'numpy.complex128'>, # Комплексные числа, в которых действительная и мнимая части представлены двумя вещественными числами типа float64.  
`complex256` <class 'numpy.clongdouble'>,
`clongdouble` <class 'numpy.clongdouble'>, 
 
`bytes_` <class 'numpy.bytes_'>, # [datatypes_bytes](./datatypes_bytes.md)
`bytes` <class 'numpy.bytes_'>,
`a` <class 'numpy.bytes_'>, 

`object_` <class 'numpy.object_'>, 
`datetime64` <class 'numpy.datetime64'>,
`timedelta64` <class 'numpy.timedelta64'>, 

`longlong` <class 'numpy.longlong'>, 
`ulonglong` <class 'numpy.ulonglong'>, 
  
`object` <class 'numpy.object_'>, 
