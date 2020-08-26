import struct

# Helper functions
class tc_virtual_type():
	@classmethod
	def getname(this):
		if hasattr( this, "__annotations__" ):
			if "c_name" in this.__annotations__:
				return this.__annotations__[ "c_name" ]
		return this.__qualname__

#
# typedef struct { ... } name ;
#
class tc_struct( tc_virtual_type ):
	def __init__( this, value = None ):
		if hasattr( this, "__annotations__" ):
			for _, value in this.__annotations__.items():
				if type(value) == tc_arr:
					setattr( this, _, tc_arr( value.type, len(value.values), value.default, value.string ))
				else:
					setattr( this, _, type(value)(value.value) )
		
	def show( this, lvl = 0 ):
		if hasattr( this, "__annotations__" ):
			for attr, value in this.__annotations__.items():
					
				value.show( lvl + 1 )
				
	#def __getattr__( this, name ):
	#	return this.__annotations__[ name ]
		
	@classmethod
	def reqinit( this ):
		if hasattr(this, "_reqinit" ): return this._reqinit
		
		if hasattr( this, "__annotations__" ):
			for _, value in this.__annotations__.items():
				if type(value) == tc_arr:
					if not value.fixed: 
						this._reqinit = True
						return this._reqinit
				# Check child structures too
				elif tc_struct in type(value).__bases__:
					if type(value).reqinit():
						this._reqinit = True
						return this._reqinit
		
		this._reqinit = False
		return this._reqinit

#
# used for builtins (float, uint32_t .. etc)
#
class tc_type( tc_virtual_type ):
	def __init__( this, default = None ):
		this.value = default
		this.align = None
	
	def __str__( this ): return str( this.value )
	
	def packed( this ):
		return struct.pack( this.__annotations__["c_layout"], int(this.value) )
		
#
# wrapper for tc_struct / type to create fixed or dynamically sized arrays
#
class tc_arr():
	def __init__( this, constr = None, num = 0, default = None, string = False ):
		this.fixed = False if num == 0 else True
		this.string = string
		this.default = default
		
		if string:
			this.type = tc_char
			this.values = [ tc_char(0) ] * num
			if default != None:
				this.strcpy( default )
		
		else:
			this.values = [ constr(default) ] * num
			this.type = constr
	
	# Append item for dynamic array
	def push( this, value ):
		if not this.fixed:
			# If not passing in object then create object from base type
			v = value if type(value) == this.type else this.type(value)
			this.values.append( v )
	
	# Allowing [] indexing		
	def __getitem__( this, key ):
		return this.values[ key ]
	
	def __setitem__( this, key, value ):
		this.values[ key ] = value
		
	# Strcpy into this buffer
	def strcpy( this, newStr ):
		if this.fixed:
			for _, ch in enumerate( newStr ):
				this.values[_] = tc_char( ord(ch) )
			this.values[len(newStr)] = tc_char( 0 )
		else:
			for ch in newStr:
				this.push( ord(ch) )
			this.push( 0 )

# Floating point types
class tc_float32( tc_type ): 	c_name: "float";		c_layout: "<f"
class tc_float64( tc_type ):	c_name: "double";		c_layout: "<d"	

# Sized signed
class tc_int8( tc_type ):		c_name: "int8_t";		c_layout: "<b"
class tc_int16( tc_type ):		c_name: "int16_t";	c_layout: "<h"
class tc_int32( tc_type ):		c_name: "int32_t";	c_layout: "<i"
class tc_int64( tc_type ):		c_name: "int64_t";	c_layout: "<l"

# Sized unsigned
class tc_uint8( tc_type ): 	c_name: "uint8_t"; 	c_layout: "<B"
class tc_uint16( tc_type ): 	c_name: "uint16_t"; 	c_layout: "<H"
class tc_uint32( tc_type ): 	c_name: "uint32_t"; 	c_layout: "<I"
class tc_uint64( tc_type ): 	c_name: "uint64_t";	c_layout: "<L"

# Other builtin
class tc_char( tc_type ):		c_name: "char";		c_layout: "<B"

#
# Generates a C header from the root structure
#
def c_header( classes ):
	def _c_header( root, isRoot = True ):
		storage = []
		init = []

		# iterate <name>: value() defines on class
		if hasattr( root, "__annotations__" ):
			for _, value in root.__annotations__.items():
				
				# Derived from class or array->class
				basetype = None
				
				if tc_arr == type(value):
					basetype = value.type
					
					# Fixed sized buffers get added to the structure definition
					# Variable size are stored somewhere else
					
					if value.fixed:
						storage.append( basetype.getname() + " " + _ + "[" + str(len(value.values)) + "];" )
					else:
						storage.append( basetype.getname() + " *" + _ + ";" )
						storage.append( "uint32_t num" + _ + ";" )
						init.append( (_,) )
				else:
					basetype = type(value)	
					storage.append( basetype.getname() + " " + _ )
					
					if hasattr( value, "align" ):
						if value.align != None:
							storage[-1] += " __attribute__((aligned(" + str(value.align) + ")))"
							
					storage[-1] += ";"
					
				# Create definitions for other structures too, if we need them
				if tc_struct in basetype.__bases__:			
					if basetype not in _c_header.written:
						_c_header.written += [basetype]
						_c_header( basetype, False )
						
					if basetype.reqinit():
						if tc_arr == type(value):
							init.append( (_, "num" + _, basetype.getname()) )
						else:
							init.append( (_, basetype.getname()) )
					
				storage.append( "" )
					
		# Write this structure
		_c_header.header_lines.append( "typedef struct" )
		_c_header.header_lines.append( "{" )
		_c_header.header_lines += [ "\t" + x for x in storage ]
		_c_header.header_lines.append( "} " + root.getname() + ";" )
		_c_header.header_lines.append( "" )
		
		# For reading this structure out of bytes
		if len(init) > 0:
			_c_header.header_lines.append( root.getname() + " * " + root.getname() + "_init(char *_self)" )
			_c_header.header_lines.append( "{" )
			_c_header.header_lines.append( "\t" + root.getname() + " *self = _self;" )
			
			for prop in init:
				if len(prop) == 1:
					_c_header.header_lines.append( "\tself->" + prop[0] + " = (char *)" + "self->" + prop[0] + " + _self;" )
				elif len(prop) == 2:
					_c_header.header_lines.append( "\t" + prop[1] + "_init( &self->" + prop[0] + " );" )
				else:
					_c_header.header_lines.append( "\tfor( int j = 0; j < self->" + prop[1] + "; j ++ ) {" )
					_c_header.header_lines.append( "\t\t" + prop[2] + "_init( self->" + prop[0] + " + j );" )
					_c_header.header_lines.append( "\t}" )
		
			_c_header.header_lines.append( "\treturn self;" )
			_c_header.header_lines.append( "}" )
			_c_header.header_lines.append( "" )
			_c_header.header_lines.append( "" )
			
	_c_header.written = []
	_c_header.header_lines = []
			
	for c in classes:
		_c_header( c )
			
	return '\n'.join( _c_header.header_lines )

#
# Inspect structure and values of _root
#
def p_values( _root ):
	def _p_values( root, lvl = 0 ):
		lines = []
		storage = []
		
		basetype = type(root)
		
		if hasattr( root, "__annotations__" ):
			for _, __ in root.__annotations__.items():
			
				value = getattr( root, _ )
			
				subtype = None
				if tc_arr == type(value):
					subtype = value.type
					
					storage.append( _ + ": " + subtype.getname() + "[" + (str(len(value.values)) if value.fixed else "*") + "] {" )
					
					if tc_type in subtype.__bases__:
						storage[-1] += " " + ', '.join( [ str(x) for x in value.values ] ) + " }"
					else:
						for n in value.values:
							storage += _p_values( n, lvl + 1 )
						storage.append( "}" )
				else:
					subtype = type(value)
					if tc_type in subtype.__bases__:
						storage.append( subtype.getname() + " " + _ + ": " + str(value.value) )
					elif tc_struct in subtype.__bases__:
						nv = _p_values( value, lvl )
						nv[0] = _ + ": " + nv[0]
						storage += nv
		
		lines.append( ("  " * lvl) + root.getname() )
		lines.append( ("  " * lvl) + "{" )
		lines += [ ("  " * (lvl+1)) + x for x in storage ]
		lines.append( ("  " * lvl) +"}" )

		return lines
	return '\n'.join( _p_values( _root ) )

# Convert object to BYTES	
def serialize( _root ):
	def s_rec( root, lvl = 0, allocHere = True ):		
		basetype = type(root)
		
		if hasattr( root, "__annotations__" ):
			for _, __ in root.__annotations__.items():
			
				value = getattr( root, _ )
			
				subtype = None
				if tc_arr == type(value):
					subtype = value.type
					
					# Fixed buffers are written in place
					if value.fixed:
						if tc_type in subtype.__bases__:
							for e in value.values:
								s_rec.bytes += e.packed()
						else:
							for e in value.values:
								s_rec( e, lvl + 1, False )
					else:
						s_rec.allocations.append( (len(s_rec.bytes), value) )
						s_rec.bytes += struct.pack( "<II", 0xFFCCFFCC, len(value.values) )
				else:
					s_rec.bytes += value.packed()
		
		if allocHere:
			for d in s_rec.allocations:
				# Correct offset from previous
				s_rec.bytes = s_rec.bytes[:d[0]] + struct.pack( "<I", len(s_rec.bytes) ) + s_rec.bytes[d[0]+4:]
				# Write da ting
				if tc_type in d[1].type.__bases__:
					for e in d[1].values:
						s_rec.bytes += e.packed()
				else:
					for e in d[1].values:
						s_rec( e, lvl, False )
				
			s_rec.allocations = []

	s_rec.bytes = b''
	s_rec.allocations = []
	s_rec( _root )
	
	return s_rec.bytes
