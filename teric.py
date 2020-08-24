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
	def __init__( this, value ):
		pass
		
	def show( this, lvl = 0 ):
		if hasattr( this, "__annotations__" ):
			for attr, value in this.__annotations__.items():
					
				value.show( lvl + 1 )
				
	def attr( this, name ):
		return this.__annotations__[ name ]

#
# used for builtins (float, uint32_t .. etc)
#
class tc_type( tc_virtual_type ):
	def __init__( this, default = None ):
		this.value = default
		
#
# wrapper for tc_struct / type to create fixed or dynamically sized arrays
#
class tc_arr():
	def __init__( this, constr, num = 0, default = None ):
		this.values = [ constr(default) ] * num
		this.fixed = False if num == 0 else True
		this.type = constr
		
class tc_float32( tc_type ): c_name: "float"

class tc_uint8( tc_type ): c_name: "uint8_t"
class tc_uint16( tc_type ): c_name: "uint16_t"
class tc_uint32( tc_type ): c_name: "uint32_t"
class tc_uint64( tc_type ): c_name: "uint64_t"

#
# Generates a C header from the root structure
#
def c_header( root, written = [], header_lines = [], isRoot = True ):
	storage = []

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
			else:
				basetype = type(value)	
				storage.append( basetype.getname() + " " + _ + ";" )
				
			# Create definitions for other structures too, if we need them
			if tc_struct in basetype.__bases__: 
				if basetype not in written:
					written += [basetype]
					c_header( basetype, written, header_lines, False )
				
			storage.append( "" )
				
	# Write this structure
	header_lines.append( "typedef struct" )
	header_lines.append( "{" )
	header_lines += [ "  " + x for x in storage ]
	header_lines.append( "} " + root.__name__ + ";" )
	header_lines.append( "" )
	
	# For reading this structure out of bytes
	if isRoot:
		header_lines.append( "void " + root.getname() + "_fix(char *arr)" )
	
	return '\n'.join( header_lines )

class my_vert( tc_struct ):
	co: tc_arr( tc_float32, 3, 0.0 )

class my_struct( tc_struct ):
	strength: 	tc_float32( default = 1.0 )
	verts: 		tc_arr( my_vert, 0, 1.0 )

print( c_header( my_struct ) )
