import struct

post_write_list = []	# Objects in this list evaluates post_write once everything is written in a byteswrite
alloc_when_list = [] # Objects in this will have their memory allocated when outside of arrays
defined_cl_list = [] # Classes currently defined while writing headers (to prevent inf-loop / multiples)

#
# Classes that inherit from tcVirtualName will have the typedef() of:
#  - the name of the derived class if no override is set
#  - the value of the annotation override 'name' is set
#
class tcVirtualName():
	@classmethod
	def typedef( cls ):
		baseclass = cls
		if hasattr( cls, "__annotations__" ):
			if "typedef" in cls.__annotations__:
				return cls.__annotations__[ "typedef" ]
		return cls.__name__
		
	@classmethod
	def funcref( cls ):
		return cls.__name__
		
	@classmethod
	def declare( cls, name ):
		return cls.typedef() + " " + name + ";"

# Atom class, aka, this object will emit bytes on the wire
class tcAtomClass( tcVirtualName ):
	def __init__( this, value ):
		this.value = value

	def duplicate( this ):
		return this.__class__( this.value )

	def serialize( this, bytes=b'' ):
		bytes += struct.pack( this.__class__.__annotations__[ "fmt" ], this.value )
		return bytes

# Built in 'atoms' (c types)
class tcFloat32( tcAtomClass ): fmt: "<f"; typedef: "float"
class tcFloat64( tcAtomClass ): fmt: "<d"; typedef: "double"

# Sized ints
class tcInt8( tcAtomClass ): 	fmt: "<b"; typedef: "int8_t"
class tcInt16( tcAtomClass ): fmt: "<h"; typedef: "int16_t"
class tcInt32( tcAtomClass ): fmt: "<i"; typedef: "int32_t"
class tcInt64( tcAtomClass ): fmt: "<l"; typedef: "int64_t"
# Unsigned variants
class tcUInt8( tcAtomClass ): fmt: "<B"; typedef: "uint8_t"
class tcUInt16( tcAtomClass ): fmt: "<H"; typedef: "uint16_t"
class tcUInt32( tcAtomClass ): fmt: "<I"; typedef: "uint32_t"
class tcUInt64( tcAtomClass ): fmt: "<L"; typedef: "uint64_t"
# Characters (uint8_t)
class tcChar( tcAtomClass ): fmt: "<B"; typedef: "char"

#
# Main structure type baseclass
#
class tcStruct( tcVirtualName ):
	@classmethod
	def declarations( cls ):
		if hasattr( cls, "__annotations__" ):
			return [ (k,v) for k,v in cls.__annotations__.items() if k not in ["typedef"] ]
		return []
	
	@classmethod
	def define( cls, lines = [] ):
		global defined_cl_list
	
		definethis = True if cls not in defined_cl_list else False
	
		if definethis:
			defined_cl_list.append( cls )
			lines.append( "struct " + cls.typedef() + "{" )
		
		for k, v in cls.declarations():
			if hasattr( v, "define" ):
				lines = v.define([]) + lines
		
			if definethis and hasattr( v, "declare" ):
				lines.append( "\t" + v.declare( k ) )
		
		if definethis:
			lines.append( "};" )
			lines.append( "" )
		
			for k, v in cls.declarations():
				if hasattr( v, "accessors" ):
					lines += v.accessors( cls, k )
			
		return lines
		
	# Instance sets up local variables based on annotations
	def __init__( this ):
		# Derive data from base class annotations
		for k, v in this.__class__.declarations():
			setattr( this, k, v.duplicate() )
	
	# Create identical instance of this instance
	def duplicate( this ):
		ob = this.__class__()
		for k, _ in this.__class__.declarations():
			setattr( ob, k, getattr( this, k ).duplicate() )
		return ob

	def serialize( this, bytes = b'' ):
		strstart = len(bytes)
		for k, v in this.__class__.declarations():
			getattr(this, k)._base = strstart
			bytes = getattr(this, k).serialize( bytes )
		
		return bytes

# Subtype pass-through
class subtyped():
	def define( this, lines = [] ):
		global defined_cl_list
		
		if this.type not in defined_cl_list and hasattr( this.type, "define" ):
			lines = this.type.define([]) + lines
		
		return lines		

	# Python [] accessing ( common for sub-typed )
	def __getitem__( this, idx ):
		return this.values[ idx ]
		
	def __setitem__( this, idx, val ):
		this.values[ idx ] = val

#
# Fixed buffers
#
class tcArray( subtyped ):
	def __init__( this, value, *argv, fromstr=None ):
		if len( argv ) > 1:
			this.values = [ tcArray( value, *argv[1:] ) for x in range(argv[0]) ]
		else:
			this.values = [ value.duplicate() for x in range(argv[0]) ]
		
		this.type = type(value)
		
		if fromstr != None:
			this.strcpy( fromstr )
			this.isstr = True
		else:
			this.isstr = False
		
	def duplicate( this ):
		ob = tcArray( this.type(None), 0 )
		ob.values = [ v.duplicate() for v in this.values ]
		ob.isstr = this.isstr
		return ob
		
	def serialize( this, bytes = b'' ):
		for v in this.values:
			v._base = this._base
			bytes += v.serialize( b'' )
		return bytes
	
	def declare( this, name ):
		spec = ""
		for w in this.getwidths():
			spec += "[" + str(w) + "]"
	
		return this.type.typedef()+" "+name+spec+";"
	
	# For multi-dimensional arrays
	def getwidths( this, ws = [] ):
		ws.append( len(this.values) )
		
		if type(this.values[0]) == tcArray:
			this.values[0].getwidths( ws )
			
		return ws
		
	# Fill internal buffer from string. May overflow, be careful!	
	def strcpy( this, string ):
		for i, ch in enumerate(string):
			this.values[i] = tcChar(ord(ch))
		this.values[len(string)] = tcChar(0)

#
# Dynamically sized array (starts at 0, .push() to add items)
#
class tcBuffer( subtyped ):
	def __init__( this, cls, fromstr=None, align=1 ):
		this.values = []
		this.type = cls
		this.align = align
		
		# If fromstr is set this object is string type
		if fromstr != None:
			this.strcpy( fromstr )
			this.isstr = True
		else:
			this.isstr = False
	
	# TC OBJECT METHODS __________________________________________________________________________
	def duplicate( this ):
		ob = tcBuffer( this.type )
		ob.values = [ v.duplicate() for v in this.values ]
		ob.isstr = this.isstr
		ob.align = this.align
		return ob
		
	def alloc_ready( this, bytes = b'' ):
		if len(bytes) % this.align != 0:
			bytes += b'\x00' * (this.align-(len(bytes) % this.align))
	
		offset = struct.pack( "<I", len(bytes) - this._base )
		bytes = bytes[:this._edit] + offset + bytes[this._edit+4:]
	
		for v in this.values:
			bytes = v.serialize( bytes )
		
		return bytes
	
	def serialize( this, bytes = b'' ):
		global alloc_when_list
	
		alloc_when_list.append(this)
		this._edit = len(bytes)
		
		bytes += b'\xBE\xEF\xCA\xFE'
		if not this.isstr:
			bytes += struct.pack( "<I", len(this.values) )
		
		return bytes
	
	def declare( this, name ):
		return "uint32_t off"+name+";"+ ("\n\tuint32_t num"+name+";" if not this.isstr else "")
	
	# Buffer object has functions to access its buffers simply
	def accessors( this, struct, name ):
		lns = []
		
		sub = this.type.typedef()
		
		func = "TC_INLINE "+sub+" *"+struct.funcref()+"_"+name+"( "+struct.typedef()	+" *self"
		lns.append( func + (" ){" if this.isstr else ", int const i ){") )
		
		if this.isstr:
			lns.append( "\treturn (char *)self + self->off"+name+";" )
		else:
			lns.append( "\treturn ("+sub+" *)((char *)self + self->off"+name+") + i;" )
		lns.append( "}\n" )
		
		return lns
		
	# UTILITY FUNCTIONS __________________________________________________________________________

	# Add a new value to buffer, automatically convert to
	# internal type if argument wasnt already
	def push( this, value ):
		if type(value) != this.type:
			this.values.append( this.type(value) )
		else:
			this.values.append( value )
	
	# Copy-convert each char of string into tcChar object and push to array
	def strcpy( this, string ):
		this.values = []
		for ch in string:
			this.values.append( tcChar(ord(ch)) )
		this.values.append( tcChar(0) )

#
# Pointer type stores reference to other object
#
class tcPointer():
	def __init__( this, typename ):
		this.typename = typename
		this.obj = None
	
	def setptr( this, obj ):
		this.obj = obj
	
	def declare( this, name ):
		return "int32_t off"+name+";"
		
	def accessors( this, struct, name ):
		lns = []
		sub = this.typename
		
		lns.append( "TC_INLINE "+sub+" *"+struct.funcref()+"_"+name+"( "+struct.typedef()+" *self ){" )
		lns.append( "\treturn (char *)self + self->off"+name+";" )
		lns.append( "}\n" )
		return lns
	
	def serialize( this, bytes = b'' ):
		global post_write_list
	
		this._edit = len(bytes)
		bytes += b'\xEE\xEE\xEE\xEE'
		post_write_list.append( this )
		return bytes

	def duplicate( this ):
		ob = tcPointer( this.typename )
		ob.obj = this.obj
		return ob

	def post_write( this, bytes=b'' ):
		offset = struct.pack( "<i", this.obj._base - this._base ) if this.obj != None else b'\x00\x00\x00\x00'
		bytes = bytes[:this._edit] + offset + bytes[this._edit+4:]
		return bytes

#
# Convert python TC object into bytes
#
def tcBytes( obj, to_file=None ):
	global post_write_list
	global alloc_when_list

	buf = b''
	buf = obj.serialize( buf )
	
	lcpy = [x for x in alloc_when_list]
	alloc_when_list = []
	
	while len(lcpy) > 0:	
		for i in lcpy:
			buf = i.alloc_ready( buf )
	
		lcpy = [x for x in alloc_when_list]
	
	for post in post_write_list:			
		buf = post.post_write(buf)
		
	if to_file != None:
		o = open( to_file, "wb" )
		o.write( buf )
		o.close()
		
	return buf

#
# Generate a header from a class type
#
def tcHeader( clss, to_file=None ):
	global defined_cl_list
	
	lines = []
	
	if type( clss ) == list:
		for cls in clss:
			lines = cls.define( lines )
			
	else:
		lines = clss.define( lines )
		
	lines = ["#define TC_INLINE inline __attribute__((always_inline))",""] + [("typedef struct "+d.typedef()+" "+d.typedef()+";") for d in defined_cl_list] + ["\n"] + lines
	
	if to_file != None:
		o = open( to_file , "w" )
		o.write( '\n'.join(lines) )
		o.close()
		
	return lines
