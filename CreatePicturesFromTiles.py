from PIL import Image, ImageOps, ImageChops
import argparse
import os
import os.path
import glob

LOG_NAME = 'CreatePicturesFromTiles_LOG.txt'
WARN = 'WARN'
ERR = 'ERR'

TOP = 0
RIGHT = 1
BOT = 2
LEFT = 3

g_do_log = False
g_log_file = None

class Tile:
	def __init__(self, im_index, im):
		self.im_index = im_index
		self.boundaries = {}
		
		#Get pixel data, a list of rows, with each row containing pixel data
		width, height = im.size
		pixels = [list(im.getdata())[i * width:(i + 1) * width] for i in range(height)]
	
		#Store border information via hashing to minimize the impact of end users
		#creating large pictures with many tiles. Hashing collisions should be rare unless
		#we start talking about billions of unique images being used as tiles
		#We can always move to md5 (which has a 128-bit space as opposed to 64-bit space) if need be.
		self.boundaries[TOP] = hash(tuple(pixels[0]))
		self.boundaries[RIGHT] = hash(tuple([row[0] for row in pixels]))
		self.boundaries[BOT] = hash(tuple(pixels[height - 1]))
		self.boundaries[LEFT] = hash(tuple([row[width - 1] for row in pixels]))
		
	def CompareBoundaries(direction, boundary):
		if boundary != None:
			return self.boundaries[direction] == boundary
		else:
			return True
	
	def GetImageIndex():
		return self.im_index
	
	def GetBoundary(direction):
		return 

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
		
def ParseCommandLineArgs():
	path_def = './'
	out_def = 'out.png'
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
	log_help = ('If set, log warnings and errors to "CreatePicturesFromTiles_LOG.txt" file. '
		'If not set, only report errors to stdout. '
		'Default: ' + str(log_def))
	no_log_help = ('If set, disable logging. Default: ' + str(not log_def))
	
	parser = argparse.ArgumentParser(description = prog_desc)
	parser.add_argument('frame_width',  type = int,                           help = frame_width_help)
	parser.add_argument('frame_height', type = int,                           help = frame_height_help)
	parser.add_argument('--path', '-p', type = str,                           help = path_help)
	parser.add_argument('--out',  '-o', type = str,                           help = out_help)
	parser.add_argument('--log',  '-l', dest = 'log', action = 'store_true',  help = log_help)
	parser.add_argument('--no-log',     dest = 'log', action = 'store_false', help = no_log_help)
	
	parser.set_defaults(path = path_def, out = out_def, log = log_def)

	args = parser.parse_args()
	
	return args

def GetTilesFromImages(im_map):
	return [Tile(im_index, im) for (im_index, im) in im_map.items()]

def GetImagesFromPath(path):
	im_list = []
	im_size = None

	if not os.path.isdir(path):
		Log(ERR, 'Input path (' + path + ') does not point to a directory')
		return {}

	files = glob.glob(os.path.join(path, '*'))
	
	for file in files:
		if not os.path.isfile(file):
			Log(WARN, 'Could not get image information from ' + file + '. File recursion not supported.')
			continue
		
		try:
			im = Image.open(file)
			
			#Restriction: All tiles must be of the same size
			if im_size == None:
				im_size = im.size
			elif im_size != im.size:
				Log(ERR, 'Image from ' + file + ' does not have the same size as image from ' + files[0] + '.')
				im.close()
				for i in im_list:
					i.close()
				return {}
				
			#To increase the number of tile combinations,
			#Add additional images to the list which are just the same image but rotated and mirrored.
			#TODO: It may be more efficient to determine the picture's symmetry and 
			#  only create additional images that are non-identical.
			for degree in [0, 90, 180, 270]:
				im_list.append(im.rotate(degree))
				im_list.append(ImageOps.mirror(im.rotate(degree))) #ImageOps.mirror flips horizontally
		except OSError as err:
			#Presumably the image files are resting in a directory with other non-image files.
			Log(WARN, str(err))
	
	#Note: Normally would delete duplicates by having images be a set and avoid a function call, 
	#but that won't work here, as each image contains some file object member.
	im_list = DeleteDuplicateImages(im_list)
	
	im_map = {k:v for k,v in enumerate(im_list)}
	
	return im_map

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

def CloseImageMap(im_map):
	for im in list(im_map.values()):
		im.close()

def Main():
	args = ParseCommandLineArgs()
	
	SetupLogging(args.log)
	
	im_map = GetImagesFromPath(args.path)
	tile_list = GetTilesFromImages(im_map)
	
	CloseImageMap(im_map)
	CloseLog()
	
if __name__ == "__main__":
	Main()