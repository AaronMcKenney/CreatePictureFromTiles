from PIL import Image, ImageOps, ImageChops
import argparse
import os
import os.path
import glob

LOG_NAME = 'CreatePicturesFromTiles_LOG.txt'
WARN = 'WARN'
ERR = 'ERR'

g_do_log = False
g_log_file = None

#class Tile:
	
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

def GetTilesFromPath(path):
	images = GetImagesFromPath(path)

def GetImagesFromPath(path):
	images = []

	if not os.path.isdir(path):
		Log(ERR, 'Input path (' + path + ') does not point to a directory')
		return []

	files = glob.glob(os.path.join(path, '*'))
	
	for file in files:
		if not os.path.isfile(file):
			Log(WARN, 'Could not get image information from ' + file + '. File recursion not supported.')
			continue
		
		try:
			image = Image.open(file)
			
			#To increase the number of tile combinations,
			#Add additional images to the list which are just the same image but rotated and mirrored.
			for degree in [0, 90, 180, 270]:
				images.append(image.rotate(degree))
				images.append(ImageOps.mirror(image.rotate(degree))) #ImageOps.mirror flips horizontally
		except OSError as err:
			Log(WARN, str(err))
	
	#Note: Normally would delete duplicates by having images be a set and avoid a function call, 
	#but that won't work here, as each image contains some file object member.
	images = DeleteDuplicateImages(images)
	
	for image in images:
		image.show()
	return images

def DeleteDuplicateImages(images):
	indices_to_del = []
	
	for i in range(len(images)):
		for j in range(i + 1, len(images)):
			if ImagesAreIdentical(images[i], images[j]):
				#There is no difference between the images. Remove the ith image
				indices_to_del.append(i)
				break
	
	#Delete duplicates from highest index to lowest index to prevent out of bound errors.
	for i in reversed(indices_to_del):
		del images[i]
	
	return images

def ImagesAreIdentical(im1, im2):
	NO_DIFF = (0,0,0,0)
	pixels = ImageChops.difference(im1, im2).getdata()
	return all(pixel == pixels[0] for pixel in pixels) and pixels[0] == NO_DIFF

def Main():
	args = ParseCommandLineArgs()
	
	SetupLogging(args.log)
	
	tile_list = GetTilesFromPath(args.path)
	
	CloseLog()
	
if __name__ == "__main__":
	Main()