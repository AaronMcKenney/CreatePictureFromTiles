from PIL import Image
import argparse

def ParseCommandLineArgs():
	tile_def = './'
	out_def = 'out.png'
	
	prog_desc = ('Given a path to a directory of tile images ' 
		'(which have the same size and can be linked without mismatching borders), ' 
		'as well as a frame width and height in terms of tiles, ' 
		'generate a picture.')
	tile_help = ('Path to a directory that only contains tiles, '
		'Default: ' + tile_def)
	out_help = ('Name of the image file to output. '
		'The name should include the extension, which dictates the image format of the output. '
		'Default: ' + out_def)
	frame_width_help = ('The width of the frame, in terms of tiles. ')
	frame_height_help = ('The height of the frame, in terms of tiles. ')
	
	parser = argparse.ArgumentParser(description = prog_desc)
	parser.add_argument('frame_width',  type=int,                     help = frame_width_help)
	parser.add_argument('frame_height', type=int,                     help = frame_height_help)
	parser.add_argument('--path', '-p', type=str, default = tile_def, help = tile_help)
	parser.add_argument('--out',  '-o', type=str, default = out_def,  help = out_help)

	args = parser.parse_args()
	
	return args

def Main():
	args = ParseCommandLineArgs()

	
if __name__ == "__main__":
	Main()