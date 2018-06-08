from PIL import Image, ImageOps, ImageChops
import argparse
import os
import os.path
import sys
import glob
import random
import re
import yaml
from copy import deepcopy

LOG_NAME = 'CreatePictureFromTiles_LOG.txt'
WARN = 'WARN'
ERR = 'ERR'

TOP = 0
RIGHT = 1
BOT = 2
LEFT = 3

g_do_log = False
g_log_file = None

class Tile:
	def __init__(self, im):
		self.im = im
		self.boundaries = {}
		
		#Get pixel data, a list of rows, with each row containing pixel data
		width, height = im.size
		pixels = [list(im.getdata())[i * width:(i + 1) * width] for i in range(height)]
		
		#Store border information via hashing to minimize the impact of end users
		#creating large pictures with many tiles. Hashing collisions should be rare unless
		#we start talking about billions of unique images being used as tiles
		#We can always move to md5 (which has a 128-bit space as opposed to 64-bit space) if need be.
		self.boundaries[TOP] = hash(tuple(pixels[0]))
		self.boundaries[RIGHT] = hash(tuple([row[width - 1] for row in pixels]))
		self.boundaries[BOT] = hash(tuple(pixels[height - 1]))
		self.boundaries[LEFT] = hash(tuple([row[0] for row in pixels]))
		
	def CompareBoundaries(self, direction, boundary):
		if boundary != None:
			return self.boundaries[direction] == boundary
		else:
			return True

def ParseCommandLineArgs():
	size_def = '(0,0)'
	grid_def = ''
	path_def = './'
	out_def = 'out.png'
	add_im_def = True
	speed_mode_def = False
	log_def = False
	
	prog_desc = ('Given a path to a directory of tile images ' 
		'(which have the same size and can be linked without mismatching borders), ' 
		'as well as a frame width and height in terms of tiles OR a pre-made grid yaml file, ' 
		'generate a picture. REQUIRES PYTHON 3 AND PILLOW')
	size_help = ('The width and height (comma-separated) of the frame in terms of tiles. '
		'Example formats: "1,2", "(1,2)". ')
	grid_help = ('filename of the grid.yaml file which contains a pre-made tile grid. '
		'If this argument is given, file size is ignored. '
		'Default: no grid file provided. ')
	path_help = ('Path to a directory that only contains tiles, '
		'Default: ' + path_def)
	out_help = ('Name of the image file to output. '
		'The name should include the extension, which dictates the image format of the output. '
		'Default: ' + out_def)
	add_help = ('If set, will try to create new images by rotating/mirroring provided ones. '
		'Use this if you have few images which exclude basic rotation possibilities. '
		'Default: ' + str(add_im_def))
	no_add_help = ('If set, will only use images provided by path. '
		'Use this if you have many images and wish to reduce computation time. '
		'Default: ' + str(not add_im_def))
	speed_help = ('If set, will use a speedier algorithm that may give poor results. '
		'Use this when you have very simple tiles that can easily be matched up. '
		'Default: ' + str(speed_mode_def))
	no_speed_help = ('If set, will use a slower algorithm that may give good results. '
		'Use this when you have a very complex series of tiles or tile grid. '
		'Default: ' + str(not speed_mode_def))
	log_help = ('If set, log warnings and errors to "CreatePicturesFromTiles_LOG.txt" file. '
		'If not set, only report errors to stdout. '
		'Default: ' + str(log_def))
	no_log_help = ('If set, disable logging. Default: ' + str(not log_def))
	
	parser = argparse.ArgumentParser(description = prog_desc)
	parser.add_argument('--size', '-s', type = str,                                  help = size_help)
	parser.add_argument('--grid', '-g', type = str,                                  help = grid_help)
	parser.add_argument('--path', '-p', type = str,                                  help = path_help)
	parser.add_argument('--out',  '-o', type = str,                                  help = out_help)
	parser.add_argument('--add',        dest = 'add_im',     action = 'store_true',  help = add_help)
	parser.add_argument('--no-add',     dest = 'add_im',     action = 'store_false', help = no_add_help)
	parser.add_argument('--fast',       dest = 'speed_mode', action = 'store_true',  help = speed_help)
	parser.add_argument('--slow',       dest = 'speed_mode', action = 'store_false', help = no_speed_help)
	parser.add_argument('--log',  '-l', dest = 'log',        action = 'store_true',  help = log_help)
	parser.add_argument('--no-log',     dest = 'log',        action = 'store_false', help = no_log_help)
	
	parser.set_defaults(size = size_def, grid = grid_def, path = path_def, out = out_def, add_im = add_im_def, speed_mode = speed_mode_def, log = log_def)

	args = parser.parse_args()
	
	return args

def SetupLogging(do_log):
	global g_do_log, g_log_file
	
	g_do_log = do_log
	if g_do_log:
		g_log_file = open(LOG_NAME, 'w')
		
def Log(level, statement):
	global g_do_log, g_log_file
	
	log_line = level + ': ' + statement + '\n'
	if g_do_log:
		g_log_file.write(log_line)
	elif level == ERR:
		print(log_line)

def CloseLog():
	global g_do_log, g_log_file
	
	if g_do_log:
		g_log_file.close()
		
		if(os.path.getsize(LOG_NAME)):
			print('Encountered warnings/errors. See ' + LOG_NAME + ' for details')
		else:
			print('No errors encountered whatsoever')

def CreatePicture(out_image_name, tile_grid, tile_map, frame_width, frame_height):
	if tile_map == [] or tile_grid == [] or frame_width <= 0 or frame_height <= 0:
		return
	
	tile_size = tile_map[tile_grid[0][0]].im.size
	new_im = Image.new('RGB', (tile_size[0]*frame_width, tile_size[1]*frame_height))
	
	for i in range(frame_height):
		for j in range(frame_width):
			box = (j*tile_size[0], i*tile_size[1], (j+1)*tile_size[0], (i+1)*tile_size[1])
			
			if tile_grid[i][j] != []:
				new_im.paste(tile_map[tile_grid[i][j]].im, box)
			else:
				#There's an error here. Place a black region instead
				new_im.paste((0,0,0), box)

	new_im.save(out_image_name)

def FastProcessTileGrid(tile_grid, tile_map, frame_width, frame_height):
	if tile_grid == []:
		return []

	#Fill tile grid from left to right, top to bottom.
	for i in range(frame_height):
		for j in range(frame_width):
			id = tile_grid[i][j]
			if i == 0 and j == 0:
				tile_grid[i][j] = random.choice(tile_grid[i][j])
				continue
			
			#Ignore tile spaces with [], as those are deemed invalid and we do not wish to propagate the error.
			exp_bound = {TOP:[], RIGHT:[], BOT:[], LEFT:[]}
			if i > 0 and tile_grid[i - 1][j] != []:
				exp_bound[TOP] = tile_map[tile_grid[i - 1][j]].boundaries[BOT]
			if i < frame_height - 1 and tile_grid[i + 1][j] != []:
				exp_bound[BOT] = list(set([tile.boundaries[TOP] for tile in [tile_map[k] for k in tile_grid[i + 1][j]]]))
			if j > 0 and tile_grid[i][j - 1] != []:
				exp_bound[LEFT] = tile_map[tile_grid[i][j - 1]].boundaries[RIGHT]
			if j < frame_width - 1 and tile_grid[i][j + 1] != []:
				exp_bound[RIGHT] = list(set([tile.boundaries[LEFT] for tile in [tile_map[k] for k in tile_grid[i][j + 1]]]))
			
			#Filter items from tile_map to match user's restrictions for this tile space
			restrict_tile_map = {k:v for k,v in tile_map.items() if k in tile_grid[i][j]}
			tile_cand_list = GetViableTiles(restrict_tile_map, exp_bound)
			
			if tile_cand_list == []:
				Log(ERR, 'Could not find any tile whose boundaries are consistent for the grid area. Using black tile to show erroneous region at position (' + str(j) + ',' + str(i) + ')')
				tile_grid[i][j] = []
			else:
				tile_grid[i][j] = random.choice(tile_cand_list)
	
	return tile_grid

def ProcessTileGrid(tile_grid, tile_map, frame_width, frame_height):
	if tile_grid == []:
		return []
	
	#Preprocessing step: Prune entries from tile_grid which are not viable.
	open_set = set()
	for i in range(frame_height):
		for j in range(frame_width):
			open_set.add((j,i))
	
	#Impossibility Pruning Loop
	while len(open_set) > 0:
		(x,y) = open_set.pop()
		indices_to_del = []
		
		#Ignore tile spaces with [], as those are deemed invalid and we do not wish to propagate the error.
		exp_bound = {TOP:[], RIGHT:[], BOT:[], LEFT:[]}
		if y > 0 and tile_grid[y - 1][x] != []:
			exp_bound[TOP] = list(set([im.boundaries[BOT] for im in [tile_map[k] for k in tile_grid[y - 1][x]]]))
		if y < frame_height - 1 and tile_grid[y + 1][x] != []:
			exp_bound[BOT] = list(set([im.boundaries[TOP] for im in [tile_map[k] for k in tile_grid[y + 1][x]]]))
		if x > 0 and tile_grid[y][x - 1] != []:
			exp_bound[LEFT] = list(set([im.boundaries[RIGHT] for im in [tile_map[k] for k in tile_grid[y][x - 1]]]))
		if x < frame_width - 1 and tile_grid[y][x + 1] != []:
			exp_bound[RIGHT] = list(set([im.boundaries[LEFT] for im in [tile_map[k] for k in tile_grid[y][x + 1]]]))
		
		for i, tile_id in enumerate(tile_grid[y][x]):
			if GetViableTiles({tile_id : tile_map[tile_id]}, exp_bound) == []:
				indices_to_del.append(i)
		
		if len(indices_to_del) > 0:
			#Delete tile_ids from highest index to lowest index to prevent out of bound errors.
			for i in reversed(indices_to_del):
				del tile_grid[y][x][i]
		
			#Since this tile_id was modified, add neighbours to the open_set
			if y > 0 and tile_grid[y - 1][x] != []:
				open_set.add((x, y - 1))
			if y < frame_height - 1 and tile_grid[y + 1][x] != []:
				open_set.add((x, y + 1))
			if x > 0 and tile_grid[y][x - 1] != []:
				open_set.add((x - 1, y))
			if x < frame_width - 1 and tile_grid[y][x + 1] != []:
				open_set.add((x + 1, y))
	
	#Fill tile grid from left to right, top to bottom.
	propogate_error = False
	for i in range(frame_height):
		for j in range(frame_width):
			if propogate_error:
				tile_grid[i][j] = []
			
			if i == 0 and j == 0:
				tile_grid[i][j] = random.choice(tile_grid[i][j])
				continue
			
			#Ignore tile spaces with [], as those are deemed invalid and we do not wish to propagate the error.
			exp_bound = {TOP:[], RIGHT:[], BOT:[], LEFT:[]}
			if i > 0 and tile_grid[i - 1][j] != []:
				exp_bound[TOP] = tile_map[tile_grid[i - 1][j]].boundaries[BOT]
			if i < frame_height - 1 and tile_grid[i + 1][j] != []:
				exp_bound[BOT] = list(set([tile.boundaries[TOP] for tile in [tile_map[k] for k in tile_grid[i + 1][j]]]))
			if j > 0 and tile_grid[i][j - 1] != []:
				exp_bound[LEFT] = tile_map[tile_grid[i][j - 1]].boundaries[RIGHT]
			if j < frame_width - 1 and tile_grid[i][j + 1] != []:
				exp_bound[RIGHT] = list(set([tile.boundaries[LEFT] for tile in [tile_map[k] for k in tile_grid[i][j + 1]]]))
			
			#Filter items from tile_map to match user's restrictions for this tile space
			restrict_tile_map = {k:v for k,v in tile_map.items() if k in tile_grid[i][j]}
			tile_cand_list = GetViableTiles(restrict_tile_map, exp_bound)

			if tile_cand_list != [] and i > 0 and j < frame_width - 1:
				#Need to also take into account the tile that was placed in the diagonally upper-right position
				#so that we don't choose a tile that will leave the grid space to the right without options
				exp_bound_right = {TOP:[], RIGHT:[], BOT:[], LEFT:[]}
				exp_bound_right[TOP] = tile_map[tile_grid[i - 1][j + 1]].boundaries[BOT]
				if i < frame_height - 1 and tile_grid[i + 1][j + 1] != []:
					exp_bound_right[BOT] = list(set([tile.boundaries[TOP] for tile in [tile_map[k] for k in tile_grid[i + 1][j + 1]]]))
				if j < frame_width - 2 and tile_grid[i][j + 2] != []:
					exp_bound_right[RIGHT] = list(set([tile.boundaries[LEFT] for tile in [tile_map[k] for k in tile_grid[i][j + 2]]]))

				right_tile_map = {k:v for k,v in tile_map.items() if k in tile_grid[i][j + 1]}
				
				indices_to_del = []
				for k, tile_cand in enumerate(tile_cand_list):
					exp_bound_right[LEFT] = tile_map[tile_cand].boundaries[RIGHT]
					if GetViableTiles(right_tile_map, exp_bound_right) == []:
						indices_to_del.append(k)
				
				if len(indices_to_del) > 0:
					#Delete tile_ids from highest index to lowest index to prevent out of bound errors.
					for k in reversed(indices_to_del):
						del tile_cand_list[k]
					
			if tile_cand_list == [] or propogate_error:
				tile_grid[i][j] = []
				
				if not propogate_error:
					Log(ERR, 'Could not find any tile whose boundaries are consistent for the grid area. '
						'Using black tile to show erroneous region at position (' + str(j) + ',' + str(i) + '). '
						'The rest of the picture from here on out will be black.')
				
				#Typically if we hit here there's something wrong with the tiles
				#that prevents them from joining up together nicely
				#It's easier on the developer's part to black out the rest of the picture
				propogate_error = True 
			else:
				tile_grid[i][j] = random.choice(tile_cand_list)

	return tile_grid
	
def GetTileGridFromFile(grid_path, tile_map):
	if grid_path == '' or tile_map == []:
		return ([], -1, -1)
	
	#Instantiate tile_grid with Nones, which will be filled in
	tile_grid = []
	(frame_width, frame_height) = (-1, -1)
	yaml_obj = None
	
	try:
		with open(grid_path) as f:
			yaml_obj = yaml.load(f)
	except Exception as err:
		Log(ERR, 'Failed to get tile grid from path "' + grid_path + '". Error message: "' + str(err) + '"')
		return ([], -1, -1)
	
	#Get Parameters from the yaml file
	id_map = {} #A map from the identifier used in the yaml file to acceptable tile_map indices
	for id, im_list in yaml_obj['id'].items():
		id_map[id] = [k for k,v in tile_map.items() if os.path.basename(v.im.filename) in im_list]
	tile_grid = deepcopy(yaml_obj['grid'])
	frame_width = len(tile_grid[0])
	frame_height = len(tile_grid)
	
	#Preprocessing Step: Replace each entry in tile grid with list of potential tile ids
	for i in range(frame_height):
		for j in range(frame_width):
			tile_grid[i][j] = deepcopy(id_map[tile_grid[i][j]])
	
	return (tile_grid, frame_width, frame_height)

def ConstructTileGrid(tile_map, frame_width, frame_height):
	if tile_map == {} or frame_width <= 0 or frame_height <= 0:
		return []
	
	#Instantiate tile_grid with each grid space having access to all tile keys
	tile_grid = []
	for i in range(frame_height):
		tile_row = []
		for j in range(frame_width):
			tile_row.append(deepcopy(list(tile_map.keys())))
		tile_grid.append(tile_row)
	
	return tile_grid

def GetViableTiles(tile_map, exp_bound):
	tile_cand_list = []
	
	for (i,tile) in tile_map.items():
		is_viable = True
		
		for dir in [TOP, RIGHT, BOT, LEFT]:
			if exp_bound[dir] == []:
				continue
			elif type(exp_bound[dir]) == int:
				is_viable &= tile.boundaries[dir] == exp_bound[dir]
			else:
				is_viable &= tile.boundaries[dir] in exp_bound[dir]
		
		if is_viable:
			tile_cand_list.append(i)
	
	return tile_cand_list

def GetTilesFromImages(im_list):
	return dict(enumerate(map(Tile, im_list)))

def GetImagesFromPath(path, add_im):
	im_list = []
	im_size = None

	if not os.path.isdir(path):
		Log(ERR, 'Input path (' + path + ') does not point to a directory')
		return []

	files = glob.glob(os.path.join(path, '*'))
	
	for file in files:
		if not os.path.isfile(file):
			Log(WARN, 'Could not get image information from ' + file + '. File recursion not supported.')
			continue
		
		try:
			im = Image.open(file)
			
			if im_size == None:
				im_size = im.size
			elif im_size != im.size:
				#Restriction: All tiles must be of the same size
				Log(ERR, 'Image from ' + file + ' does not have the same size as image from ' + files[0] + '.')
				im.close()
				for i in im_list:
					i.close()
				return []
			
			#To increase the number of tile combinations,
			#Add additional images to the list which are just the same image but rotated and mirrored.
			if add_im:
				#TODO: It may be more efficient to determine the picture's symmetry and 
				#  only create additional images that are non-identical.
				degrees = [0, 180]
				if im_size[0] == im_size[1]: #if image is square we can add more rotations without consequence
					degrees += [90, 270]
				
				for degree in degrees:
					new_im1 = im.rotate(degree)
					new_im1.filename = file #Workaround for filename attribute error
					im_list.append(new_im1)
					
					new_im2 = ImageOps.mirror(im.rotate(degree)) #ImageOps.mirror flips horizontally
					new_im2.filename = file #Workaround for filename attribute error
					im_list.append(new_im2)
			else:
				im_list.append(im)
		except OSError as err:
			#Presumably the image files are resting in a directory with other non-image files.
			Log(WARN, str(err))
	
	#Note: Normally would delete duplicates by having images be a set and avoid a function call, 
	#but that won't work here, as each image contains some file object member.
	im_list = DeleteDuplicateImages(im_list)
	
	if im_list == []:
		Log(ERR, 'Could not find any image files in ' + path)
	
	return im_list

def DeleteDuplicateImages(im_list):
	indices_to_del = []
	
	for i in range(len(im_list)):
		for j in range(i + 1, len(im_list)):
			if ImagesAreIdentical(im_list[i], im_list[j]):
				#There is no difference between the images. Remove the ith image
				indices_to_del.append(i)
				break
	
	#Delete duplicates from highest index to lowest index to prevent out of bound errors.
	for i in reversed(indices_to_del):
		del im_list[i]
	
	return im_list

def ImagesAreIdentical(im1, im2):
	NO_DIFF = (0,0,0,0)
	pixels = ImageChops.difference(im1, im2).getdata()
	return all(pixel == pixels[0] for pixel in pixels) and pixels[0] == NO_DIFF

def GetFrameSizeFromStr(size_str):
	#allow for various ways of sending in frame size, including "1,1" and "(1,1)"
	size_str_arr = re.split('\s|,', size_str)
	
	if len(size_str_arr) != 2:
		Log(ERR, 'Could not retrieve frame width and height from ' + size_str)
		return (-1,-1)
	
	size_int_arr = []
	for i, size_str in enumerate(size_str_arr):
		frame_log_str = 'width'
		if i == 1:
			frame_log_str = 'height'
			
		size_int_str = ''.join(filter(lambda x: x.isdigit(), size_str))
		
		if size_int_str == '':
			Log(ERR, 'Could not retrieve frame ' + frame_log_str + ' from "' + size_str + '"')
			return (-1, -1)	
		if int(size_int_str) <= 0:
			Log(ERR, 'Got a number <= 0 for frame ' + frame_log_str)
			return (-1, -1)
		
		size_int_arr.append(int(size_int_str))
		
	return tuple(size_int_arr)

def CloseImages(im_list):
	for im in im_list:
		im.close()

def Main():
	args = ParseCommandLineArgs()
	
	SetupLogging(args.log)
	
	(frame_width, frame_height) = (-1, -1)
	tile_grid = []
	
	im_list = GetImagesFromPath(args.path, args.add_im)
	tile_map = GetTilesFromImages(im_list)
	
	if args.grid == '':
		(frame_width, frame_height) = GetFrameSizeFromStr(args.size)
		tile_grid = ConstructTileGrid(tile_map, frame_width, frame_height)
	else:
		grid_path = os.path.join(args.path, args.grid)
		(tile_grid, frame_width, frame_height) = GetTileGridFromFile(grid_path, tile_map)
	
	if args.speed_mode:
		FastProcessTileGrid(tile_grid, tile_map, frame_width, frame_height)
	else:
		ProcessTileGrid(tile_grid, tile_map, frame_width, frame_height)
	
	CreatePicture(args.out, tile_grid, tile_map, frame_width, frame_height)
	
	CloseImages(im_list)
	CloseLog()
	
if __name__ == "__main__":
	Main()