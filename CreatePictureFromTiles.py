from PIL import Image, ImageOps, ImageChops
import argparse
import os
import os.path
import glob
import random

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
	
	def GetImage(self):
		return self.im
	
	def GetBoundary(self, direction):
		return self.boundaries[direction]

def ParseCommandLineArgs():
	path_def = './'
	out_def = 'out.png'
	add_im_def = True
	log_def = False
	
	prog_desc = ('Given a path to a directory of tile images ' 
		'(which have the same size and can be linked without mismatching borders), ' 
		'as well as a frame width and height in terms of tiles, ' 
		'generate a picture. REQUIRES PYTHON 3 AND PILLOW')
	frame_width_help = ('The width of the frame, in terms of tiles. ')
	frame_height_help = ('The height of the frame, in terms of tiles. ')
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
	log_help = ('If set, log warnings and errors to "CreatePicturesFromTiles_LOG.txt" file. '
		'If not set, only report errors to stdout. '
		'Default: ' + str(log_def))
	no_log_help = ('If set, disable logging. Default: ' + str(not log_def))
	
	parser = argparse.ArgumentParser(description = prog_desc)
	parser.add_argument('frame_width',  type = int,                              help = frame_width_help)
	parser.add_argument('frame_height', type = int,                              help = frame_height_help)
	parser.add_argument('--path', '-p', type = str,                              help = path_help)
	parser.add_argument('--out',  '-o', type = str,                              help = out_help)
	parser.add_argument('--add',        dest = 'add_im', action = 'store_true',  help = add_help)
	parser.add_argument('--no-add',     dest = 'add_im', action = 'store_false', help = no_add_help)
	parser.add_argument('--log',  '-l', dest = 'log',    action = 'store_true',  help = log_help)
	parser.add_argument('--no-log',     dest = 'log',    action = 'store_false', help = no_log_help)
	
	parser.set_defaults(path = path_def, out = out_def, add_im = add_im_def, log = log_def)

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
	if tile_map == [] or tile_grid == []:
		return
	
	tile_size = tile_map[tile_grid[0][0]].GetImage().size
	new_im = Image.new('RGB', (tile_size[0]*frame_width, tile_size[1]*frame_height))
	
	for i in range(frame_height):
		for j in range(frame_width):
			box = (j*tile_size[0], i*tile_size[1], (j+1)*tile_size[0], (i+1)*tile_size[1])
			
			if tile_grid[i][j] != -1:
				new_im.paste(tile_map[tile_grid[i][j]].GetImage(), box)
			else:
				#There's an error here. Place a black region instead
				new_im.paste((0,0,0), box)

	new_im.save(out_image_name)

def ConstructTileGrid(tile_map, frame_width, frame_height):
	if tile_map == {}:
		return []
	
	#Instantiate tile_grid with Nones, which will be filled in
	tile_grid = [[None]*frame_width for _ in range(frame_height)]
	
	#Fill tile grid from left to right, top to bottom.
	for i in range(frame_height):
		for j in range(frame_width):
			if i == 0 and j == 0:
				tile_grid[0][0] = random.choice(list(tile_map.keys()))
				continue
			
			exp_bound = {TOP:None, RIGHT:None, BOT:None, LEFT:None}
			if i > 0 and tile_grid[i - 1][j] != -1:
				exp_bound[TOP] = tile_map[tile_grid[i - 1][j]].GetBoundary(BOT)
			if j > 0 and tile_grid[i][j - 1] != -1:
				exp_bound[LEFT] = tile_map[tile_grid[i][j - 1]].GetBoundary(RIGHT)
			
			tile_cand_list = GetViableTiles(tile_map, exp_bound)
			if tile_cand_list == []:
				Log(ERR, 'Could not find any tile whose boundaries are consistent for the grid area. Using black tile to show erroneous region at position (' + str(j) + ',' + str(i) + ')')
				tile_cand_list = [-1]
			
			tile_grid[i][j] = random.choice(tile_cand_list)
	
	return tile_grid

def GetViableTiles(tile_map, exp_bound):
	tile_cand_list = []
	
	for (i,tile) in tile_map.items():
		is_viable = True
		
		for dir in [TOP, RIGHT, BOT, LEFT]:
			is_viable &= exp_bound[dir] == None or tile.GetBoundary(dir) == exp_bound[dir]
		
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
					im_list.append(im.rotate(degree))
					im_list.append(ImageOps.mirror(im.rotate(degree))) #ImageOps.mirror flips horizontally
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

def CloseImages(im_list):
	for im in im_list:
		im.close()

def Main():
	args = ParseCommandLineArgs()
	
	SetupLogging(args.log)
	
	if args.frame_width <= 0 or args.frame_height <= 0:
		Log(ERR, 'frame width and height must be greater than 0')
		return
	
	im_list = GetImagesFromPath(args.path, args.add_im)
	tile_map = GetTilesFromImages(im_list)
	tile_grid = ConstructTileGrid(tile_map, args.frame_width, args.frame_height)
	CreatePicture(args.out, tile_grid, tile_map, args.frame_width, args.frame_height)
	
	CloseImages(im_list)
	CloseLog()
	
if __name__ == "__main__":
	Main()