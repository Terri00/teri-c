# Terri-c (teric?)

> *This project is under active development and is a subset of the teri-c pre-compiler library. Some features may be missing, if so, suggest it as an issue!*

Teric is a read-only fast file format spec generator for C programs. It allows you to manage data types for your games or other realtime applications completely within python, as well as generate the format header ready to be `#include`ed.

The design is made to have a balance between file size, and access speed from within memory. 

If you want to load any format created with teric, you simply load all the bytes from a file or other buffer, and cast that to a pointer of the header. Then you can use it! no marshaling steps take place which means you can also throw around the memory without arrays breaking, or any setup costs. You can also just `free( ptr )` the whole file when you dont need it anymore.

## General Usage
In Teric you construct your formats using python classes and annotations.
A teric structure shall derive from the baseclass `tcStruct`. Here is an example format:
```python
class my_struct( tcStruct ):
   version: tcInt32( 10 )
   string:  tcBuffer( tcChar, fromstr="Hello world!" )
```
When we call `tcHeader( my_struct )`, we get an array of strings that can be written to a header file which ends up looking like this:
```c
typedef struct my_struct my_struct;

struct my_struct {
   int32_t version;
   uint32_t offstring;
};

char * my_struct_string( my_struct *self ){
   return (char *)self + self->offstring;
}
```
So now we have an effective structure of C code that we can use to navigate data that we've read in earlier. We can also generate this data from python! Calling `tcBytes()` on an instance of my_struct gives us a compiled binary which we can put in a file, QR code or whatever you like really its up to you.

# The different teric classes
 `tcStruct`  is the baseclass you use the most and is the only valid object base to generate a header from. Derive all your writable structures from this.
 
## Array
`tcArray( item, *num, fromstr="" )`

Theres a few ways to define an array attribute, these are fixed sized buffers and manifest in the C code as `name type[3]`. 
- Strings: `hello: tcArray( tcChar(0), 23, fromstr="" )` Make sure fromstr is set explicitly.
- Array of ints: `numbers: tcArray( tcInt32(12), 8 )` This sets up a 8 element array of ints that all default to 12
- Multi-dimensional array: `matrix: tcArray( tcFloat32(0), 4, 4 )` It makes a 4x4 floating point matrix

## Buffer
`tcBuffer( cls, fromstr="" )`

This is similar to tcArray except the buffer has variable size. Therefore, it does not contribute in size to the host structure ( apart from 8 bytes for mapping ), and the memory goes elsewhere. To setup a buffer you construct it with the class type as cls (not instance), and same as before if you want it as string, set `fromstr=""`

In the C code you will get some extra function to access elements from this buffer, if you setup an array on a structure called `my_struct` like so: `pickles: tcBuffer( pickle )`, you get in c:
```c
pickle * my_struct_pickles( my_struct *self, int const i );

// To loop elements:

for( int i = 0; i < pData->numpickles; i ++ ){ 
   pickle *o = my_struct_pickles( pData, i );
   // Do something with o ...
}
```

### Builtin types:
Teric comes with a few builtin 'atom' types to use as a surrogate for the c equivalent.
They are either standard types, or defined in <stdint.h>
| Name | C-Typedef | Width (bytes) |
|--|--|--|
| tcChar | char | 1 |
| tcFloat32 | float | 4 |
| tcFloat64 | double | 8 |
| tcUInt8 | uint8_t | 1 |
| tcUInt16 | uint16_t | 2 |
| tcUInt32 | uint32_t | 4 |
| tcUInt64 | uint64_t | 8 |
| tcInt8 | int8_t | 1 |
| tcInt16 | int16_t | 2 |
| tcInt32 | int32_t | 4 |
| tcInt64 | int64_t | 8 |

### License:
Contact me if your like microsoft or something. Otherwise do what you want, its free
