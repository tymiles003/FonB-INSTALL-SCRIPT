#!/usr/bin/env python
import sys, urllib2, tarfile, zipfile, os, getpass, stat, StringIO, platform, shutil, glob, re
from optparse import OptionParser
from distutils import spawn
from ConfigParser import RawConfigParser

Errors = []

class Install(object):
	"""
	Initialize an object of this class to start installation
	"""
	INSTALL_PATH = "/usr/local/src/PhoneB"
	PORT = "8080"

	def __init__(self):
		global Errors
		log("Creating config files")
		self.PHP_CGI_PATH = "/opt/php5.4/bin/php-cgi"
		self.create_config_files()

		active_calls = ActiveCallsSetup()
		log("Modifying %s for setting up Active Calls" % active_calls.config_file)
		if active_calls.setup():
			log("%s successfully modified." % active_calls.config_file)
		else:
			error = "[ WARNING ]: Couldn't modify %s. Active Calls wont work without it. Check %s for details" % (active_calls.config_file, "https://github.com/aptus/FonB-Documentation/blob/master/INSTALLATION/INSTALLATION.md#59-modify-extensions_customconf-to-enable-active-calls")
			Errors.append(error)
			log(error)

		log("PhoneB installation completed.")
		self.add_mobile_config()
		self.activate()
		log("Trying to start phoneb. By executing /etc/init.d/phoneb start")
		result  = os.system("/etc/init.d/phoneb restart")
		if result != 0:
			log("Error occured in starting PhoneB. Try running this script with root privilleges or setup init.d script manually.")

	def activate(self):
		config_parser = FonbConfigParser()
		config_parser.read("/etc/phoneb/phoneb.cfg")
		if not (config_parser.has_section("Demo_License_FonB_V1") or config_parser.has_section("License_FonB_V1") or config_parser.has_section("License_FonB_Mobile_V1") or config_parser.has_section("License_FonB_Highrise_V1") ):
			log("Attempting to activate phoneb")
			os.system(os.path.join(self.INSTALL_PATH, "bin", "./phoneb --activate"))
	

	def create_config_files(self):
		config_path =  "/etc/phoneb/"
		self.create_phoneb_config_file(config_path)
		self.create_users_config_file(config_path)
	
	def create_phoneb_config_file(self, config_path):
		"""
		Sets up general setup parameters for FonB
		"""
		global Errors
		config = FonbConfigParser()
		log("Creating phoneb.cfg file")
		config.read("/etc/phoneb/phoneb.cfg")
		cdr_setup = CDRSettings()
		data = {
			"PhoneB" : {
				"BaseDir" : self.INSTALL_PATH,
				"UsersConfFile" : os.path.join(config_path, "users.cfg"),
				"ListenPort" : self.PORT,
				"LameExec" : LameCheck(self.INSTALL_PATH).get_path(),
				"Debug" : "1",
				"PhpCgiPath" : self.PHP_CGI_PATH,
				"AsteriskMonitorPath" : "/var/spool/asterisk/monitor",
			},
			"WebServer" : {
				"Debug" : "1"
			},
			"WebSocket": {
				"Debug" : "1",
				"EnableAmiUpdates" : "1",
				"EnableSummaryUpdates" : "1",
				"EnableHangupUpdates" : "1",
				"EnableFeedbackUpdates" : "1",
				"EnableErrorUpdates" : "1",
				"EnableClientActionUpdates" : "1"
			},
			#"MysqlFonB": MySQLSettings().get(),
			"AMI" : AMISettings().get(),
			"MysqlCdr" : cdr_setup.get(),
		}
		data["MysqlFonB"] = data["MysqlCdr"]
		del data["MysqlFonB"]["Table"]
		cdr_columns_added = False
		if data["MysqlFonB"]["Username"] == "root":
			cdr_columns_added = cdr_setup.add_highrise_columns(data["MysqlFonB"]["Username"], data["MysqlFonB"]["Password"], data["MysqlCdr"]["Database"])
		if not cdr_columns_added:
			cdr_columns_added = cdr_setup.add_highrise_columns(data["MysqlCdr"]["Username"], data["MysqlCdr"]["Password"], data["MysqlCdr"]["Database"])		
			if not cdr_columns_added:
				error = "[ WARNING ]: Couldn't alter cdr table and add columns for highrise notes. May be columns already exist. If they don't,  check https://github.com/aptus/FonB-Documentation/blob/master/INSTALLATION/INSTALLATION.md#58-modify-asterisk-mysql-cdr-db-for-highrise-entries for how to set them up manually."
				Errors.append(error)
				log(error)
		config.parse_dict_to_config(data)
		file = open(os.path.join(config_path, "phoneb.cfg"), "w")
		config.write(file)
		log("phoneb.cfg created")
		file.close()

	def add_mobile_config(self):
		if os.access("/etc/asterisk/iax_custom.conf", os.W_OK):
			log("Writing fonb mobile config in /etc/asterisk/iax_custom.conf")
			iax_file = open("/etc/asterisk/iax_custom.conf")
			if "#include iax_fonb_mobile.conf" not in iax_file.read():
				iax_file.close()
				iax_file = open("/etc/asterisk/iax_custom.conf", "a")
				iax_file.write("\n#include iax_fonb_mobile.conf")
				iax_file.close()


	def create_users_config_file(self, config_path):
		"""
		Creates users.cfg if it doesn't exist and adds one extension
		"""
		config = FonbConfigParser()
		log("Checking for users.cfg")
		if os.access(os.path.join(config_path, "users.cfg"), os.R_OK):
			config.read("/etc/phoneb/users.cfg")
		log("Creating users.cfg file")
		exisiting_extensions_parser = RawConfigParser()
		log("Attempting to import existing extensions.")
		config_files = glob.glob("/etc/asterisk/*.conf")
		for config_file in config_files:
			try:
				exisiting_extensions_parser.read(config_file)
			except:
				pass
		for section in exisiting_extensions_parser.sections():
			if section.isdigit():
				terminal = ""
				context = ""
				try:
					terminal = exisiting_extensions_parser.get(section, "dial")
					context = exisiting_extensions_parser.get(section, "context")
				except:
					pass
				if terminal and context:
					log("Found extension: %s" % section)
					config.add_section(section)
					config.set(section, "Extension", section)
					config.set(section, "Terminal", terminal)
					config.set(section, "Context", context)
					callerid = ""
					try:
						callerid = exisiting_extensions_parser.get(section, "callerid")
					except:
						pass
					if callerid:
						config.set(section, "Name", callerid.split()[:-1][0])
					else:
						config.set(section, "Name", "")
					config.set(section, ";Password", "set the password, only 5 users can have password in a demo license.")
					config.set(section, "Mobile", "")
					config.set(section, "BaseDir", self.INSTALL_PATH)
					config.set(section, "Language", "en")
					config.set(section, "Department", "")
					config.set(section, "Company", "")
					config.set(section, "Spy", "all")
		file = open(os.path.join(config_path, "users.cfg"), "w")
		config.write(file)
		log("users.cfg created")
		file.close()

def version():
	"""
	Called when script is run with -v argument.
	Shows current version of this script
	"""
	log("FonB Installation Script v0.01")
	log("FonB v1.0.5")

class FonbConfigParser(RawConfigParser):
	optionxform = str
	allow_no_value = True
	ordered_sections = dict()
	def parse_dict_to_config(self, data):
		"""
		Parse a dictionary to build config file sections and values
		"""
		for section, options in data.iteritems():
			if section not in self.sections():
				self.add_section(section)
			for key,value in options.iteritems():
				self.set(section, key, value)
	def add_comment(self, section, comment):
		self.set(section, '; %s' % (comment,), None)

	def write(self, fp):
		"""Write an .ini-format representation of the configuration state."""
		if self._defaults:
			fp.write("[%s]\n" % ConfigParser.DEFAULTSECT)
			for (key, value) in self._defaults.items():
				self._write_item(fp, key, value)
			fp.write("\n")
		for section in self._sections:
			fp.write("[%s]\n" % section)
			if section in self.ordered_sections:
				for key in self.ordered_sections[section]:
					self._write_item(fp, key, None)
					self.remove_option(section, key)
			for (key, value) in self._sections[section].items():
				self._write_item(fp, key, value)
			fp.write("\n")

	def set_bulk(self, section, values):
		if isinstance(values, list):
			if not self.has_section(section):
				self.add_section(section)
			self.ordered_sections[section] = values
		elif isinstance(values, dict):
			for key, value in values.iteritems():
				self.set(section, key, value)
			
	def _write_item(self, fp, key, value):
		if value is None:
			fp.write("%s\n" % (key,))
		elif key != "__name__":
			fp.write("%s = %s\n" % (key, str(value).replace('\n', '\n\t')))

	def get(self, section, option):
		val = RawConfigParser.get(self, section, option)
		return val.strip('"').strip("'")

class AMISettings(object):
	"""
	Parses Asterisk manager.conf file and gets AMI credentials
	"""
	def __init__(self, ami_config_path='/etc/asterisk/manager.conf'):
		self.ami_config_path = ami_config_path

	def get(self):
		log("Setting up active calls. If this step is skipped, active calls won't work.")
		ami_data = {
			"ManagerHost" : "localhost",
			"ManagerPort" : "",
			"ManagerUsername" : "",
			"ManagerPassword" : "",
			"Debug" : "1",
		}
		while not os.access(self.ami_config_path, os.R_OK):
			log("AMI file not found or not readable.")
			self.ami_config_path = self.ami_config_path
			if self.ami_config_path == 's':
				self.ami_config_path = ''
				break
		if self.ami_config_path:
			log("Reading %s" % self.ami_config_path)
			config = FonbConfigParser()
			file = open(self.ami_config_path)
			config.readfp(file)
			ami_data["ManagerHost"] = "localhost"
			ami_data["ManagerUsername"] = [user for user in config.sections() if user != "general"][0]
			ami_data["ManagerPassword"] = config.get(ami_data["ManagerUsername"], "secret")
			ami_data["ManagerPort"] = config.get("general", "port")
			log("AMI credentials received, as long as they were correct in manager.conf, active calls should work.")
			file.close()
		else:
			log("%s file not found or not readable. Skipping AMI setup. You can set it up later manually." % (self.ami_config_path))
		return ami_data

class CDRSettings(object):
	"""
	Takes care of getting cdr settings and building dictionary
	"""

	def __init__(self, cdr_config_path='/etc/asterisk/cdr_mysql.conf'):
		"""
		Initialize cdr_config_path either as default value or with the value that user supplied
		"""
		self.cdr_config_path = cdr_config_path
		self.config = FonbConfigParser()
	def get(self):
		"""

		"""
		global Errors
		cdr_config_path = self.cdr_config_path
		data = {
			'Username' : '',
			'Password' : '',
			'Database' : '',
			'Hostname' : '',
			'Table' : 'cdr'
		}
		log("Trying to get cdr credentials from %s" % (cdr_config_path))
		while not os.access(cdr_config_path, os.R_OK):
			log("File not found or read permissions denied in %s" % (cdr_config_path))
			cdr_config_path = cdr_config_path
		if cdr_config_path:
			file = open(cdr_config_path)
			self.config.readfp(file)
			data['Username'] = self.config.get("global", "user")
			data['Password'] = self.config.get("global", "password")
			data['Hostname'] = self.config.get("global", "hostname")
			data['Database'] = self.config.get("global", "dbname")
		else:
			error = "[ ERROR ]: Couldn't read CDR settings. Call history wont work without it. Set it up manually in /etc/phoneb/phoneb.conf"
			Errors.append(error)
			log(error)
		return data

	def add_highrise_columns(self, username, password, database):
		 db = Mysql(username, password, database)
		 status = db.has_column("cdr", "FonBCallUniqueID") or db.query("ALTER TABLE cdr ADD FonBCallUniqueID VARCHAR(80) NOT NULL;") == 0
		 status = status and (db.has_column("cdr", "FonBCallNotes") or db.query("ALTER TABLE cdr ADD FonBCallNotes VARCHAR(80) NOT NULL;") == 0)
		 status = status and (db.has_column("cdr", "FonBHighriseNoteID") or db.query("ALTER TABLE cdr ADD FonBHighriseNoteID VARCHAR(80) NOT NULL;") == 0)
		 return status


class MySQLSettings(object):
	def __init__(self):
		log("Configuring FonB database")


	def get(self):
		log("FonB needs access to a MySQL database to store data. Please provide MySQL username, password and database name.")
		data = {
			"Username" : raw_input("Mysql username[root]:") or "root",
			"Password" : getpass.getpass("Password:"),
			"Database" : raw_input("Database Name[fonb]:") or "fonb",
			"Hostname" : raw_input("Hostname[localhost]:") or "localhost",
		}
		self.db = Mysql(data["Username"], data["Password"])
		if data['Username'] == 'root' and data['Hostname'] == 'localhost':
			self.create_db(data["Database"])
		elif data['Hostname'] == 'localhost':
			self.check_db(**data)
		else:
			log("Couldn't verify MySQL credentials. We hope they were alright.")
		return data

	def create_db(self, database_name):
		global Errors
		log("Woohoo! got root access to MySQL. Trying to create fonb database.")
		return_code = self.db.query("create database if not exists %s;" % (database_name))
		if return_code != 0:
			error = "[ ERROR ]: Problem in creating database. Check your MySQL credentials."
			Errors.append(error)
			log(error)
		else:
			log("MySQL Database is available.")

	def check_db(self, Username, Password, Database, **kwargs):
		global Errors
		log("Verifying MySQL credentials.")
		if Password:
			response = os.popen("mysql -u %s -p'%s' -e \"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '%s';\"" % (Username, Password, Database)).readlines()
		else:
			response = os.popen("mysql -u %s -e \"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '%s';\"" % (Username, Database)).readlines()
		if len(response) > 1:
			log("MySQL credentials verified.")
		else:
			error = "[ WARNING ]: There was some problem in verifying MySQL credentials. Make sure they were alright. You can edit them later in /etc/phoneb/phoneb.cfg"
			Errors.append(error)
			log(error)

class GlibcCheck(object):
	def __init__(self, install_path):
		self.install_path = install_path

	def check(self):
		global Errors
		output = os.popen("%s --version 2>&1" % os.path.join(self.install_path, "bin", "phoneb")).readlines()
		if "ld-linux.so" in output[0]:
			error = "[ ERROR ]: Glibc problem detected. Fix it by installing glibc.i686 package."
			log(error)
			Errors.append(error)
			os.system("yum install -y glibc.i686")
			output = os.popen("%s --version 2>&1" % os.path.join(self.install_path, "bin", "phoneb")).readlines()
			if "ld-linux.so" not in output[0]:
				log("Problem Fixed.")
				Errors = Errors[:-1]
		elif "APTUS" not in output[0]:
			error = "[ ERROR ]: Unknown error occured while executing phoneb binary. Data: %s" % output[0]
			log(error)
			Errors.append(error)


class LameCheck(object):

	def __init__(self, install_path):
		self.lame_path = os.path.join(install_path, "bin/lame")

	def get_path(self):
		log("Checking lame installation")
		return_code = os.system("%s --help > /dev/null" % self.lame_path)
		if return_code == 0:
			log("PhoneB lame is working fine. No need to compile.")
			return self.lame_path
		else:
			system_lame_path = spawn.find_executable("lame")
			if system_lame_path and os.system("%s --help > /dev/null" % system_lame_path) == 0:
				log("System already has lame available. Skipping compilation.")
				return system_lame_path
			else:
				log("Lame not working properly. Compiling it from source.")
				self.compile()
				system_lame_path = spawn.find_executable("lame")
				return system_lame_path
	
	def compile(self):
		global Errors
		return_code = os.system("cd /usr/src && wget http://sourceforge.net/projects/lame/files/lame/3.98.4/lame-3.98.4.tar.gz && tar -xf lame-3.98.4.tar.gz && cd lame-3.98.4 && ./configure && make && make install")
		if return_code != 0:
			error = "[ ERROR ]: Couldn't compile lame properly. Call recording wont work without lame."
			log(error)
			Errors.append(error)

class ActiveCallsSetup(object):
	"""
	See https://github.com/aptus/FonB-Documentation/blob/master/INSTALLATION/INSTALLATION.md#59-modify-extensions_customconf-to-enable-active-calls
	
	Reads /etc/asterisk/extensions_custom.conf
	and appends following:
	[OnHold]
	exten => s,1,Answer()
	;exten => s,2,MusicOnHold()
	exten => s,2,Hangup

	exten => hold,1,Answer()
	exten => hold,n,MusicOnHold(,3600)
	exten => hold,n,Hangup

	exten => wait,1,NoCDR()
	;exten => wait,n,StopMixMonitor()
	exten => wait,n,Answer()
	exten => wait,n,UserEvent(FonBCallSwitch,Channel: ${CHANNEL(name)})
	exten => wait,n,Wait(50)
	exten => wait,n,Hangup

	[Conference]
	exten =>  Conference,1,MeetMe(${MEETME_ROOMNUM},dqMx)

	;Conference test extension: admin
	exten =>  admin,1,MeetMe(${MEETME_ROOMNUM},qdMxp)
	exten =>  admin,n,MeetMeAdmin(${MEETME_ROOMNUM},K)

	[Hangup]
	exten => Hangup,1,NoCDR()
	exten => Hangup,n,Hangup()
	"""
	
	def __init__(self, config_file="/etc/asterisk/extensions_custom.conf"):
		self.can_access = False
		self.config_file = config_file
		self.set_config_parser()

	def set_config_parser(self):
		config_parser = FonbConfigParser()
		if os.access(self.config_file, os.W_OK) or (os.access("/etc/asterisk", os.W_OK) and not os.path.exists(self.config_file)):
			self.can_access = True
			try:
				config_parser.OPTCRE = re.compile(
			        r'(?P<option>[^\[]*)'          
			        r'(?P<vi>[^\[]*)'              
			        r'(?P<value>[^\[]*)$'
			        )
				config_parser.read(self.config_file)
				self.config_parser = config_parser
			except:
				pass

	def setup(self):

		if self.can_access:
			file_sections = self.config_parser.sections()
			for section in ["OnHold", "Conference", "Hangup"]:
				if section not in file_sections:
					self.config_parser.add_section(section)
			self.config_parser.set_bulk("OnHold", [
				"exten => s,1,Answer()",
				";exten => s,2,MusicOnHold()",
				"exten => s,2,Hangup",
				"exten => hold,1,Answer()",
				"exten => hold,n,MusicOnHold(,3600)",
				"exten => hold,n,Hangup",
				"exten => wait,1,NoCDR()",
				";exten => wait,n,StopMixMonitor()",
				"exten => wait,n,Answer()",
				"exten => wait,n,UserEvent(FonBCallSwitch,Channel: ${CHANNEL(name)})",
				"exten => wait,n,Wait(50)",
				"exten => wait,n,Hangup",
				])
			self.config_parser.set_bulk("Conference", [
				"exten =>  Conference,1,MeetMe(${MEETME_ROOMNUM},dqMx)",
				";Conference test extension: admin",
				"exten =>  admin,1,MeetMe(${MEETME_ROOMNUM},qdMxp)",
				"exten =>  admin,n,MeetMeAdmin(${MEETME_ROOMNUM},K)",
				])
			self.config_parser.set_bulk("Hangup", [
				"exten => Hangup,1,NoCDR()",
				"exten => Hangup,n,Hangup()",
				])
			fp = open(self.config_file, "w")
			self.config_parser.write(fp)
			fp.close()
			log("Restarting asterisk")
			os.system("service asterisk restart")
			return True
		else:
			return False


class Mysql(object):
	"""
	A very pathetic hack to query mysql
	"""
	def __init__(self, username, password, database="mysql"):
		self.username = username
		self.password = password
		self.database = database

	def query(self, query):
		if self.password:
			command = "mysql -u %s -p'%s' %s -e '%s' > /dev/null 2>&1" % (self.username, self.password, self.database, query)
			response = os.system(command)
			#log("Executed command %s. Response: \n %s" % (command, response))
			return response
		else:
			command = "mysql -u %s %s -e '%s' > /dev/null 2>&1" % (self.username, self.database, query)
			response = os.system(command)
			#log("Executed command %s. Response: \n %s" % (command, response))
			return response

	def result(self, query):
		if self.password:
			command = "mysql -u %s -p'%s' %s -e '%s'" % (self.username, self.password, self.database, query)
			response = os.popen(command)
			#log("Executed command %s. Response: \n %s" % (command, response))
			return response
		else:
			command = "mysql -u %s %s -e '%s'" % (self.username, self.database, query)
			response = os.popen(command)
			#log("Executed command %s. Response: \n %s" % (command, response))
			return response

	def has_column(self, table, column):
		query = "SHOW COLUMNS FROM %s LIKE \"%s\";" % (table, column)
		response = self.result(query)
		if len(response.readlines()) > 1:
			return True
		else:
			return False

class Uninstall(object):
	"""
	Deletes phoneb basedir, freepbx module and drops database
	"""
	def __init__(self):
		self.error_happened = False
		self.config_parser = FonbConfigParser()
		self.can_read = self.config_parser.read("/etc/phoneb/phoneb.cfg")
		if not self.can_read:
			self.error_happened = True
			log("[ ERROR ]: /etc/phoneb/phoneb.cfg not found.")
		else:
			self.remove_base_dir()
			self.remove_db()
			self.remove_freepbx()
			self.remove_init()
		if self.error_happened:
			log("[ ERROR ]: Uninstall finished with errors.")
		else:
			log("FonB Uninstalled succesfully.")

	def remove_base_dir(self):
		base_dir = self.config_parser.get("PhoneB", "BaseDir")
		log("Deleting files in %s" % base_dir)
		try:
			shutil.rmtree(base_dir)
		except:
			log("[ ERROR ]: Basedir %s either doesn't exist or permissions denied." % base_dir)
			self.error_happened = True

	def remove_db(self):
		username = self.config_parser.get("MysqlFonB", "Username")
		if username:
			log("Dropping database.")
			database = self.config_parser.get("MysqlFonB", "Database")
			db = Mysql(username,self.config_parser.get("MysqlFonB", "Password"),database)
			response = db.query("drop database %s;" % database)
			if response != 0:
				log("[ ERROR ]: Couldn't drop database %s" % database)
				self.error_happened = True
			else:
				log("Database dropped.")
		else:
			log("[ ERROR ]: Username not found in phoneb.cfg")
			self.error_happened = True

	def remove_freepbx(self):
		if os.path.exists("/var/www/html/admin/modules/fonbadmin"):
			log("Uninstalling Freepbx module...")
			return_code = os.system("amportal a ma uninstall fonbadmin")
			if return_code == 0:
				os.system("amportal a ma reload")
			else:
				log("[ ERROR ]: Something didn't go well while removing freepbx FonB module.")
				self.error_happened = True

	def remove_init(self):
		if os.access("/etc/init.d/phoneb", os.W_OK):
			log("Removing init script")
			os.remove("/etc/init.d/phoneb")
			log("init script removed")

log_file = open("fonb-setup.log", "w")

def log(message):
	print(message)
	log_file.write("%s \n" % message)

#equivalent of 	C int main(){...}
if __name__ == "__main__":

	"""
	Define possible command line arguments and help
	"""
	parser = OptionParser(description = "Install Aptus FonB")
	parser.add_option('-i', '--install', help = "Download and install FonB", action="store_true")
	parser.add_option('-v', '--version', action="store_true", help = "Show installation script version")
	parser.add_option('-f', '--freepbx', action="store_true", help = "Install Freepbx module")
	parser.add_option('-u', '--uninstall', action="store_true", help = "Uninstall FonB")
	cmd_args, crap = parser.parse_args()

	"""
	Print help if no args supplied and install if install arg is supplied
	"""
	if len(sys.argv) < 2:
		parser.print_help()
	elif cmd_args.install:
		Install()
	elif cmd_args.version:
		version()
	elif cmd_args.uninstall:
		Uninstall()
	log('\n'.join(Errors))
	log_file.close()