import sys, os

line_count = 0

class variable:
	name = "unknown"
	def __init__(self, args, name):
		global line_count
		self.name = name
		self.line = line_count
	def emit_declaration(self):
		return ["\tint %s;" % self.name]
	def linedef(self):
		return "#line %d" % self.line
	def emit_secure(self):
		return []

class var_any(variable):
	def __init__(self, args, name):
		variable.__init__(self, args, name)

class var_range(variable):
	def __init__(self, args, name):
		variable.__init__(self, args, name)
		self.min = args[0]
		self.max = args[1]
	def emit_secure(self):
		return [self.linedef(), "obj->%s = netobj_clamp_int(obj->%s, %s, %s);" % (self.name, self.name, self.min, self.max)]
	
class var_clientid(variable):
	def __init__(self, args, name):
		variable.__init__(self, args, name)
	def emit_secure(self):
		return [self.linedef(), "obj->%s = netobj_clamp_int(obj->%s, -1, MAX_CLIENTS);" % (self.name, self.name)]

class var_string(variable):
	def __init__(self, args, name):
		variable.__init__(self, args, name)

class object:
	def __init__(self, line):
		fields = line.split()
		self.name = fields[1]
		self.extends = None
		if len(fields) == 4 and fields[2] == "extends":
			self.extends = fields[3]
		self.enum_name = "NETOBJTYPE_%s" % self.name.upper()
		self.struct_name = "NETOBJ_%s" % self.name.upper()
		self.members = []
		
	def parse(self, lines):
		global line_count
		for index in xrange(0, len(lines)):
			line_count += 1
			line = lines[index]
			if not len(line):
				continue
				
			if line == "end":
				return lines[index+1:]
			else:
				# check for argument
				fields = line.split(")", 1)
				if len(fields) == 2:
					names = [line.strip() for line in fields[1].split(",")]
					l = fields[0].split("(", 1)
					type = l[0]
					args = [line.strip() for line in l[1].split(",")]
				else:
					l = fields[0].split(None, 1)
					type = l[0]
					args = []
					names = [line.strip() for line in l[1].split(",")]
					
				for name in names:
					create_string = 'var_%s(%s, "%s")' % (type, args, name)
					new_member = eval(create_string)
					self.members += [new_member]
				
		raise BaseException("Parse error")
	
	def emit_declaration(self):
		lines = []
		if self.extends:
			lines += ["struct %s : public NETOBJ_%s\n {" % (self.struct_name, self.extends.upper())]
		else:
			lines += ["struct %s\n {" % self.struct_name]
		for m in self.members:
			lines += m.emit_declaration()
		lines += ["};"]
		return lines

	def emit_secure(self):
		lines = []
		for m in self.members:
			lines += m.emit_secure()
		return lines
		
class event(object):
	def __init__(self, line):
		object.__init__(self, line)
		self.enum_name = "NETEVENTTYPE_%s" % self.name.upper()
		self.struct_name = "NETEVENT_%s" % self.name.upper()

class raw_reader:
	def __init__(self):
		self.raw_lines = []
	def parse(self, lines):
		global line_count
		for index in xrange(0, len(lines)):
			line_count += 1
			line = lines[index]
			if not len(line):
				continue
				
			if line == "end":
				return lines[index+1:]
			else:
				self.raw_lines += [line]
				
		raise BaseException("Parse error")		

class proto:
	def __init__(self):
		self.objects = []
		self.source_raw = []
		self.header_raw = []


def load(filename):
	# read the file
	global line_count
	line_count = 0
	lines = [line.strip() for line in file(filename).readlines()]
	
	p = proto()

	while len(lines):
		line_count += 1
		line = lines[0]
		line = line.split("//", 2)[0] # strip comment
		
		if not len(line):
			del lines[0]
			continue
			
		fields = line.split(None, 1)
		
		del lines[0]
		
		if fields[0] == "object" or fields[0] == "msg":
			new_obj = object(line)
			lines = new_obj.parse(lines)
			p.objects += [new_obj]
		elif fields[0] == "event":
			new_obj = event(line)
			lines = new_obj.parse(lines)
			p.objects += [new_obj]
		elif fields[0] == "raw_source":
			raw = raw_reader()
			lines = raw.parse(lines)
			p.source_raw += raw.raw_lines
		elif fields[0] == "raw_header":
			raw = raw_reader()
			lines = raw.parse(lines)
			p.header_raw += raw.raw_lines
		else:
			print "error, strange line:", line
			
	return p
	
def emit_header_file(f, p):
	for l in p.header_raw:
		print >>f, l
		
	if 1: # emit the enum table
		print >>f, "enum {"
		print >>f, "\tNETOBJTYPE_INVALID=0,"
		for obj in p.objects:
			print >>f, "\t%s," % obj.enum_name
		print >>f, "\tNUM_NETOBJTYPES"
		print >>f, "};"
		print >>f, ""

	print >>f, "int netobj_secure(int type, void *data, int size);"
	print >>f, "const char *netobj_get_name(int type);"
	print >>f, "int netobj_num_corrections();"
	print >>f, ""

	for obj in p.objects:
		for l in obj.emit_declaration():
			print >>f, l
		print >>f, ""
			
def emit_source_file(f, p, protofilename):
	
	
	print >>f, "#line 1 \"%s\"" % os.path.abspath(protofilename).replace("\\", "\\\\")
	
	for l in p.source_raw:
		print >>f, l

	print >>f, ""
	print >>f, "static int num_corrections = 0;"
	print >>f, "int netobj_num_corrections() { return num_corrections; }"
	print >>f, ""
	print >>f, "static int netobj_clamp_int(int v, int min, int max)"
	print >>f, "{"
	print >>f, "\tif(v<min) { num_corrections++; return min; }"
	print >>f, "\tif(v>max) { num_corrections++; return max; }"
	print >>f, "\treturn v;"
	print >>f, "}"
	print >>f, ""
	
	if 1: # names
		print >>f, "static const char *object_names[] = {"
		print >>f, "\t" + '"invalid",'
		for obj in p.objects:
			print >>f, '\t"%s",' % obj.name
		print >>f, '\t""'
		print >>f, "};"
		print >>f, ""

	if 1: # secure functions
		print >>f, "static int secure_object_invalid(void *data, int size) { return 0; }"
		for obj in p.objects:
			print >>f, "static int secure_%s(void *data, int size)" % obj.name
			print >>f, "{"
			print >>f, "\t%s *obj = (%s *)data;" % (obj.struct_name, obj.struct_name)
			print >>f, "\t(void)obj;" # to get rid of "unused variable" warning
			print >>f, "\tif(size != sizeof(%s)) return -1;" % obj.struct_name
			if obj.extends:
				print >>f, "\tif(secure_%s(data, sizeof(NETOBJ_%s)) != 0) return -1;" % (obj.extends, obj.extends.upper())
				
			for l in obj.emit_secure():
				print >>f, "\t" + l
			print >>f, "\treturn 0;";
			print >>f, "}"
			print >>f, ""

	if 1: # secure function table
		print >>f, "typedef int(*SECUREFUNC)(void *data, int size);"
		print >>f, "static SECUREFUNC secure_funcs[] = {"
		print >>f, "\t" + 'secure_object_invalid,'
		for obj in p.objects:
			print >>f, "\tsecure_%s," % obj.name
		print >>f, "\t" + '0x0'
		print >>f, "};"
		print >>f, ""

	if 1:
		print >>f, "int netobj_secure(int type, void *data, int size)"
		print >>f, "{"
		print >>f, "\tif(type < 0 || type >= NUM_NETOBJTYPES) return -1;"
		print >>f, "\treturn secure_funcs[type](data, size);"
		print >>f, "};"
		print >>f, ""

	if 1:
		print >>f, "const char *netobj_get_name(int type)"
		print >>f, "{"
		print >>f, "\tif(type < 0 || type >= NUM_NETOBJTYPES) return \"(invalid)\";"
		print >>f, "\treturn object_names[type];"
		print >>f, "};"
		print >>f, ""
	
if sys.argv[1] == "header":
	p = load(sys.argv[2])
	emit_header_file(file(sys.argv[3], "w"), p)
elif sys.argv[1] == "source":
	p = load(sys.argv[2])
	emit_source_file(file(sys.argv[3], "w"), p, sys.argv[2])
else:
	print "invalid command"
	sys.exit(-1)
