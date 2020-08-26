import struct

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

	def serialize( this, bytes=b'', allocate = [] ):
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

class tcStruct( tcVirtualName ):
	@classmethod
	def declarations( cls ):
		if hasattr( cls, "__annotations__" ):
			return [ (k,v) for k,v in cls.__annotations__.items() if k not in ["typedef"] ]
		return []
	
	@classmethod
	def define( cls, lines = [], defined = [] ):
		defined.append( cls )
		lines.append( "struct " + cls.typedef() + "{" )
		
		getters = []
		
		for k, v in cls.declarations():
			if v.__class__ not in defined and hasattr( v, "define" ):
				lines = v.define([], defined) + lines
		
			lines.append( "\t" + v.declare( k ) )
			
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

	def serialize( this, bytes = b'', allocate = [] ):	
		for k, v in this.__class__.declarations():
			getattr(this, k)._base = len(bytes)
			bytes = getattr(this, k).serialize( bytes, allocate )
		
		return bytes

# Subtype pass-through
class subtyped():
	def define( this, lines = [], defined = [] ):
		
		if this.type not in defined and hasattr( this.type, "define" ):
			lines = this.type.define([], defined) + lines
		
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
		
	def serialize( this, bytes = b'', allocate = [] ):
		for v in this.values:
			v._base = this._base
			bytes += v.serialize( b'', allocate )
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
	def __init__( this, cls, fromstr=None ):
		this.values = []
		this.type = cls
		
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
		return ob
		
	def alloc_ready( this, bytes = b'', allocate = [] ):
		offset = struct.pack( "<I", len(bytes) - this._base )
		bytes = bytes[:this._edit] + offset + bytes[this._edit+4:]
	
		for v in this.values:
			bytes = v.serialize( bytes, allocate )
		
		return bytes
	
	def serialize( this, bytes = b'', allocate = [] ):
		allocate.append(this)
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
# Convert python TC object into bytes
#
def tcBytes( obj ):
	ac = []	
	buf = b''

	buf = obj.serialize( buf, ac )
	
	while len(ac) > 0:
		newreq = []
	
		for i in ac:
			buf = i.alloc_ready( buf, newreq )
	
		ac = newreq
		
	return buf

#
# Generate a header from a class type
#
def tcHeader( cls, defs = [] ):
	lines = cls.define([], defs)
	
	return [("typedef struct "+d.typedef()+" "+d.typedef()+";") for d in defs] + ["\n"] + lines


# ~~ USER ~~

class v3layer( tcStruct ):
	typedef:		"v3layer_t"	
	name:			tcArray( tcChar(0), 16, fromstr="[none]" )

class v3model( tcStruct ):
	typedef:		"v3model_t"

	version:		tcInt32( 3 )
	name:			tcBuffer( tcChar, fromstr="" )

	layers:		tcBuffer( v3layer )

test = v3model()
test.layers.push( v3layer() )

print( '\n'.join(tcHeader(v3model)) )
print( tcBytes(test).hex() )
