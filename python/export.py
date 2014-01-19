#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright 2013-2014 Nathanaël Jourdane
# This file is part of Zazouck.
# Zazouck is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version.
# Zazouck is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General Public License for more details.
# You should have received a copy of the GNU General Public License along with Zazouck. If not, see <http://www.gnu.org/licenses/>.

import time, os, re, tempfile
import solid, stl
from os import path as op
import subprocess
import shlex
import signal

class Export: # TODO : singleton

	def __init__(self, openscad_path, corners_table_path, edges_table_path, zazouck_scad_dir,
			nb_job_slots, verbose_lvl, test):
		self.openscad_path = openscad_path
		self.corners_table_path = corners_table_path
		self.edges_table_path = edges_table_path
		self.zazouck_scad_dir = zazouck_scad_dir
		self.nb_job_slots = nb_job_slots
		self.verbose_lvl = verbose_lvl
		self.test = test
		self.process = list() # liste de tuples (retour process, nom du fichier)
		self.nb_created = 0
		signal.signal(signal.SIGINT, self.signal_handler)

		if test:
			print "Note: you are in testing mode - don't print these files."


	def _get_nb_lines(self, input_path):
		with open(input_path, 'r') as f_input:
			for nb_lines, line in enumerate(f_input):
				pass
		return nb_lines + 1

	def _print_status(self, i, nb_corners, t_init, picture=False):
		f_type = "picture" if picture else "stl file"
		print "Compiling " + f_type + " " + str(i+1) + "/" + str(nb_corners),
		print "(" + str(int(round(i/float(nb_corners)*100))) + "%)",
		if i==0:
			print "- please wait... "
		else:
			spent = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time()-t_init))
			remaining = time.strftime("%Hh%Mm%Ss", time.gmtime((time.time()-t_init)/i*(nb_corners-i)))
			print "- started for " + spent + ", please wait", remaining + "."


	def make_tables(self, input_stl_path, details_path, start_from, finish_at, shuffle):
		print "\n*** Creating tables ***\n"
		cleaned_path = op.join(tempfile.gettempdir(), "zazouck_cleaned")

		stl.clean_file(input_stl_path, cleaned_path)
		model = stl.file_to_model(cleaned_path)
		os.remove(cleaned_path)
		
		s = solid.Solid()
		s.fill_corners(model)
		s.fill_polygons(model)
		del model
		
		s.set_connected_corners()
		s.set_corners_data()

		s.fill_edges()
		s.set_edges_data()
		#s.merge_coplanar_polygons() # TODO

		s.build_corners_table(self.corners_table_path, start_from, finish_at, shuffle)
		s.build_edges_table(self.edges_table_path, start_from, finish_at, shuffle)		
		print "Successfully created table files in " + op.dirname(self.corners_table_path) + "."

		if details_path != None:
			s.display(details_path)

	def make_documentation(self, doc_dir):
		img_dir = op.join(doc_dir, "img")

		os.makedirs(img_dir)
		self.make_pictures(img_dir, 200)

	def make_pictures(self, img_dir, pict_width):
		scad_name = "corner_light.scad" if self.test else "corner.scad"
		corner_scad_path = op.join(self.zazouck_scad_dir, scad_name)
		extra_options = "--imgsize=" + str(pict_width*2) + "," + str(pict_width*2) + \
				" --camera=0,0,0,45,0,45,140"
		print "\n*** Creating pictures ***\n"

		self._start_processes(corner_scad_path, self.corners_table_path, img_dir, "png", extra_options)

		dimentions = str(pict_width) + 'x' + str(pict_width) # 
		process_image = 'mogrify -trim +repage -resize ' + dimentions + \
				' -background "#FFFFE5" ' + '-gravity center -extent ' + dimentions + \
				' -fuzz 5% -transparent "#FFFFE5" ' + op.join(img_dir, "*.png")
		subprocess.Popen(shlex.split(process_image))

	def make_corners(self, corners_dir):
		scad_name = "corner_light.scad" if self.test else "corner.scad"
		corner_scad_path = op.join(self.zazouck_scad_dir, scad_name)		
		print "\n*** Creating corners ***\n"

		self._start_processes(corner_scad_path, self.corners_table_path, corners_dir, "stl")

		print "\nFinished!", self.nb_created, "stl files successfully created in " + corners_dir + "."

	def make_edges(self, edges_dir):
		scad_name = "corner_light.scad" if self.test else "corner.scad"
		nb_edges = self._get_nb_lines(self.edges_table_path)-2
		print "\n*** Creating edges ***\n"

		corner_scad_path = op.join(self.zazouck_scad_dir, scad_name)

	def _start_processes(self, scad_path, table_path, output_dir, extension, extra_options = ""):
		nb_files = self._get_nb_lines(table_path) - 2

		with open(table_path, 'r') as table:
			print "Model details: " + table.readline().rstrip('\n').replace(",", ", ") + "."
			print nb_files, extension, "files will be created in " + output_dir + "."

			table.readline()
			t_init = time.time()
			self.nb_created = 0

			if self.nb_job_slots == 1:
				print "Compiling the first " + extension + " file, please wait...\n"
			else:
				nb_creating = self.nb_job_slots if self.nb_job_slots < nb_files else nb_files
				print "Compiling", nb_creating, extension, "files simultaneously, please wait...\n"

			for line in table:
				corner_id = line[0:line.index(",")]
				start = [m.start() for m in re.finditer(r",",line)][3] + 1 # position des données
				data = line.rstrip('\n')[start:]
				options = "-D 'id=" + corner_id + "; angles=\"" + data + "\"' " + extra_options
				output_path = op.join(output_dir, corner_id + "." + extension)
				self._openscad(scad_path, options, output_path)
				self._end_of_process(nb_files, t_init)

			while self.process:
				self._end_of_process(nb_files, t_init)

	def _end_of_process(self, nb_files, t_init):
		spent = time.strftime("%Hh%Mm%Ss", time.gmtime(time.time() - t_init))
		for i, p in enumerate(self.process):
			if p[0].poll() == 0:
				del self.process[i]
				self.nb_created += 1
				progress = str(self.nb_created) + "/" + str(nb_files)
				print spent + ": Created file " + progress + ": " + p[1] + "."

	def make_model(self, stls_dir, full_model_path):
		import shutil

		print "\n*** Creating full model ***\n"
		print "This file will be created in " + full_model_path

		temp_path = op.join(tempfile.gettempdir(), "full_model")
		if os.path.exists(temp_path):
			shutil.rmtree(temp_path)
		os.makedirs(temp_path)

		corner_move_scad_path = op.join(self.zazouck_scad_dir, "move_part.scad")

		with open(self.corners_table_path, 'r') as f_table:
			f_table.readline()
			f_table.readline()
			
			for i, line in enumerate(f_table): # utiliser start_processes ?
				data = line.split(",")[0:4]
				file_name = data[0] + ".stl"
				options = "-D 'file=\"" + op.join(stls_dir, file_name) + "\"; " + \
						"tx=" + data[1] + "; ty=" + data[2] + "; tz=" + data[3] + "'"
				output_file = op.join(temp_path, "moved_" + file_name)
				self._openscad(corner_move_scad_path, options, output_file)

		#with open(self.edges_table_path, 'r') as f_table:


	def _openscad(self, scad_file_path, options, output_file):
		cmd = self.openscad_path + " " + scad_file_path + " -o " + output_file + " " + options

		if self.verbose_lvl >= 1:
			print ">>>" + cmd
		err = None if self.verbose_lvl >= 2 else open(os.devnull, 'w')
		out = None if self.verbose_lvl == 3 else open(os.devnull, 'w')

		p = subprocess.Popen(shlex.split(cmd), stdout = out, stderr = err)
		self.process.append((p,op.basename(output_file)))

		if len(self.process) >= self.nb_job_slots:
			p.wait()

	def signal_handler(self, signal, frame):
		import sys
		print "\n\nCompilation interrupted by the user."
		print self.nb_created, "file" + ("s" if self.nb_created > 1 else "") + " were created."
		print "Tip : You can continue this work with -s option."
		sys.exit(0)