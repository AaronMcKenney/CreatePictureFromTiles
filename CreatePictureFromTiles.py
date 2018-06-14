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

#Log Consts
LOG_NAME = 'CreatePictureFromTiles_LOG.txt'
WARN = 'WARN'
ERR = 'ERR'

#Direction Consts
TOP = 0
RIGHT = 1
BOT = 2
LEFT = 3

#For 2-tuples
X = 0
Y = 1

#YUV Format Chroma Channels
YUV_Y = 0
YUV_U = 1
YUV_V = 2

#Speed Mode Consts
NORMAL = 0
FAST = 1
NO_COMPARE = 2

#Global Vars
g_do_log = False
g_log_file = None
g_err_occurred = False

#Deblocking related tables 
MIN_QP = 0
MAX_QP = 51
VERT_EDGE = 0
HORZ_EDGE = 1
#Tables from "Understanding in-loop filtering in the HEVCvideo standard", Mihir Mody - June 21, 2013
#valid between [0,51]
QP_2_BETA_TABLE = [
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0, 
	 6,  7,  8,  9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 20, 22, 24,
	26, 28, 30, 32, 34, 36, 38, 40, 42, 44, 46, 48, 50, 52, 54, 56, 
	58, 60, 62, 64
]
#valid between [0,53]
QP_2_TC_TABLE = [
	 0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,  0,
	 1,  1,  1,  1,  1,  1,  1,  1,  1,  2,  2,  2,  2,  3,  3,  3,  3,  4,
	 4,  4,  5,  5,  6,  6,  7,  8,  9, 10, 11, 13, 14, 16, 18, 20, 22, 24
]

class Tile:
	def __init__(self, im):
		self.im = im
		self.boundaries = {}
		
		#Get pixel data, a list of rows, with each row containing pixel data
		width, height = im.size
		pixels = [list(im.getdata())[i * width:(i + 1) * width] for i in range(height)]
		
		self.boundaries[TOP] = hash(tuple((pixels[0])))
		self.boundaries[RIGHT] = hash(tuple([row[width - 1] for row in pixels]))
		self.boundaries[BOT] = hash(tuple(pixels[height - 1]))
		self.boundaries[LEFT] = hash(tuple([row[0] for row in pixels]))
		
	def CompareBoundaries(self, dir, boundaries):
		if boundaries == []:
			return True #Either at the edge of the frame or boundaries is erroneous and anything goes.
		elif len(boundaries) == 1:
			return self.boundaries[dir] == boundaries[0]
		else:
			return self.boundaries[dir] in boundaries

def ParseCommandLineArgs():
	size_def = '(0,0)'
	grid_def = ''
	path_def = './'
	out_def = 'out.png'
	speed_mode_def = 0
	add_im_def = True
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
	speed_help = ('0: Puts tiles together slowly in an attempt to mitigate misplacements. '
		'Use this when you have a complex set of tiles wherein not every combination will fit together. '
		'1: Puts tiles together quickly while also trying to make sure that they fit together. '
		'Use this when you know that a tile can fit in any given space and the boundaries have to match. '
		'2: Puts tiles together without caring about whether or not the boundaries match. '
		'Default: ' + str(speed_mode_def))
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
	parser.add_argument('--size',       '-s', type = str,                                  help = size_help)
	parser.add_argument('--grid',       '-g', type = str,                                  help = grid_help)
	parser.add_argument('--path',       '-p', type = str,                                  help = path_help)
	parser.add_argument('--out',        '-o', type = str,                                  help = out_help)
	parser.add_argument('--speed_mode', '-m', type = int,                                  help = speed_help)
	parser.add_argument('--add',              dest = 'add_im',     action = 'store_true',  help = add_help)
	parser.add_argument('--no_add',           dest = 'add_im',     action = 'store_false', help = no_add_help)
	parser.add_argument('--log',  '-l',       dest = 'log',        action = 'store_true',  help = log_help)
	parser.add_argument('--no_log',           dest = 'log',        action = 'store_false', help = no_log_help)
	
	parser.set_defaults(size = size_def, grid = grid_def, path = path_def, out = out_def, add_im = add_im_def, speed_mode = speed_mode_def, log = log_def)

	args = parser.parse_args()
	
	return args

def SetupLogging(do_log):
	global g_do_log, g_log_file
	
	g_do_log = do_log
	if g_do_log:
		g_log_file = open(LOG_NAME, 'w')
		
def Log(level, statement):
	global g_do_log, g_log_file, g_err_occurred
	
	log_line = level + ': ' + statement + '\n'
	if g_do_log:
		g_log_file.write(log_line)
	elif level == ERR:
		print(log_line)
		g_err_occurred = True

def CloseLog():
	global g_do_log, g_log_file
	
	if g_do_log:
		g_log_file.close()
		
		if(os.path.getsize(LOG_NAME)):
			print('Encountered warnings/errors. See ' + LOG_NAME + ' for details')
		else:
			print('No errors encountered whatsoever')

def CreatePictureFromTileGrid(tile_grid, tile_map, frame_width, frame_height):
	if tile_map == [] or tile_grid == [] or frame_width <= 0 or frame_height <= 0:
		return None
	
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

	return new_im

def OverwriteTuple(tup, idx, val):
	#Since tuples are immutable, we have to do a dirty hack to alter single elements within.
	lst = list(tup)
	lst[idx] = val
	return tuple(lst)

def clip(lower, upper, x):
	return int(max(lower, min(x, upper)))

#VERT EDGE DEBLOCKING:
#p30 p20 p10 p00 | q00 q10 q20 q30
#p31 p21 p11 p01 | q01 q11 q21 q31
#p32 p22 p12 p02 | q02 q12 q22 q32
#p33 p23 p13 p03 | q03 q13 q23 q33
#HORZ EDGE DEBLOCKING:
#p30 p31 p32 p33
#p20 p21 p22 p23
#p10 p11 p12 p13
#p00 p01 p02 p03
#---------------
#q00 q01 q02 q03
#q10 q11 q12 q13
#q20 q21 q22 q23
#q30 q31 q32 q33
#WHERE q00 refers to the pixel at the top-left position of the 4x4 block that we're looking at. 
def HEVCDeblock4x4(pix, q_pos, beta, tc, cc, qp, edge):

	#Initialize temporary pixel data
	p = [[0]*4 for i in range(4)]
	q = [[0]*4 for i in range(4)]
	if edge == VERT_EDGE:
		for i in range(4):
			for j in range(4):
				p[i][j] = pix[q_pos[X] - i - 1, q_pos[Y] + j][cc]
				q[i][j] = pix[q_pos[X] + i, q_pos[Y] + j][cc]
	else: #edge == HORZ_EDGE
		for i in range(4):
			for j in range(4):
				p[i][j] = pix[q_pos[X] + j, q_pos[Y] - i - 1][cc]
				q[i][j] = pix[q_pos[X] + j, q_pos[Y] + i][cc] 
		
	#dp0 = |p2,0-2*p1,0+p0,0|
	dp0 = abs(p[2][0] - 2*p[1][0] + p[0][0])
	#dp3 =|p2,3-2*p1,3+p0,3|
	dp3 = abs(p[2][3] - 2*p[1][3] + p[0][3])
	#dq0 = |q2,0-2*q1,0+q0,0|
	dq0 = abs(q[2][0] - 2*q[1][0] + q[0][0])
	#dq3 = |q2,3-2*q1,3+q0,3|
	dq3 = abs(q[2][3] - 2*q[1][3] + q[0][3])	
	
	dpq0 = dp0 + dq0
	dpq3 = dp3 + dq3
	dp = dp0 + dp3
	dq = dq0 + dq3
	
	if cc == YUV_Y:
		if dpq0 + dpq3 > beta:
			#Apply some kind of filter.
			
			#|p2,i−2p1,i+p0,i|+|q2,i−2q1,i+q0,i| < beta / 8 for i = 0 and 3
			low_spatial_activity = (dpq0 < beta / 8) and (dpq3 < beta / 8)
			#|p3,i−p0,i|+|q0,i−q3,i| < beta / 8 for i = 0 and 3
			flat_signal = (abs(p[3][0] - p[0][0]) + abs(q[0][0] - q[3][0]) < beta / 8) and (abs(p[3][3] - p[0][3]) + abs(q[0][3] - q[3][3]) < beta / 8)
			#|p0,i−q0,i| < 2.5tC for i = 0 and 3
			low_intens_thresh = (abs(p[0][0] - q[0][0]) < 2.5 * tc) and (abs(p[0][3] - q[0][3]) < 2.5 * tc)
			if low_spatial_activity and flat_signal and low_intens_thresh:
				#Perform strong deblocking
				cs = 2 * QP_2_TC_TABLE[qp + 2]
				
				for i in range(4): #For every line in the 4x4 block.
					#P-BLOCK
					#δp0s = (p2+2p1−6p0+2q0+q1+4)≫3
					dp0s_no_clip = (p[2][i] + 2*p[1][i] - 6*p[0][i] + 2*q[0][i] + q[1][i] + 4) >> 3
					dp0s = clip(-cs, cs, dp0s_no_clip)
					#δp1s = (p2−3p1+p0+q0+2)≫2
					dp1s_no_clip = (p[2][i] - 3*p[1][i] + p[0][i] + q[0][i] + 2) >> 2
					dp1s = clip(-cs, cs, dp1s_no_clip)
					#δp2s = (2p3−5p2+p1+p0+q0+4)≫3
					dp2s_no_clip = (2*p[3][i] - 5*p[2][i] + p[1][i] + p[0][i] + q[0][i] + 4) >> 3
					dp2s = clip(-cs, cs, dp2s_no_clip)
					
					#Q-BLOCK
					#δq0s = (q2+2q1−6q0+2p0+p1+4)≫3
					dq0s_no_clip = (q[2][i] + 2*q[1][i] - 6*q[0][i] + 2*p[0][i] + p[1][i] + 4) >> 3
					dq0s = clip(-cs, cs, dq0s_no_clip)
					#δp1s = (p2−3p1+p0+q0+2)≫2
					dq1s_no_clip = (q[2][i] - 3*q[1][i] + q[0][i] + p[0][i] + 2) >> 2
					dq1s = clip(-cs, cs, dq1s_no_clip)
					#δp2s = (2p3−5p2+p1+p0+q0+4)≫3
					dq2s_no_clip = (2*q[3][i] - 5*q[2][i] + q[1][i] + q[0][i] + p[0][i] + 4) >> 3
					dq2s = clip(-cs, cs, dq2s_no_clip)
					
					#Update temporary pixels with strong filtering
					p[0][i] += dp0s
					p[1][i] += dp1s
					p[2][i] += dp2s
					q[0][i] += dq0s
					q[1][i] += dq1s
					q[2][i] += dq2s
			else:
				#Perform normal deblocking
				c0 = QP_2_TC_TABLE[qp + 2] #qp + 2 due to boundary strength being 2.
				c1 = QP_2_TC_TABLE[qp + 2] / 2 #qp + 2 due to boundary strength being 2.
				for i in range(4): #For every line in the 4x4 block.
					#δ0=(9(q0−p0)−3(q1−p1)+8)≫4.
					d0_no_clip = (9*(q[0][i] - p[0][i]) - 3*(q[1][i] - p[1][i]) + 8) >> 4
					
					#If this doesn't hold, then it is likely that the change of signal on both sides  
					#  of the block boundary is caused by a natural edge and not by a blocking artifact.
					#As such, do not perform deblocking for this line.
					if abs(d0_no_clip) < 10 * tc:
						d0 = clip(-c0, c0, d0_no_clip)
						
						dp1 = 0
						if dp < (3.0/16.0) * beta:
							#δp1=(((p2+p0+1)≫1)−p1+Δ0)≫1
							dp1_no_clip = (((p[2][i] + p[0][i] + 1) >> 1) - p[1][i] + d0) >> 1
							dp1 = clip(-c1, c1, dp1_no_clip)
						
						dq1 = 0
						if dq < (3.0/16.0) * beta:
							#δq1=(((q2+q0+1)≫1)−q1-Δ0)≫1
							dq1_no_clip = (((q[2][i] + q[0][i]) >> 1) - q[1][i] - d0) >> 1
							dq1 = clip(-c1, c1, dq1_no_clip)
						
						#Update temporary pixels with normal filtering
						#p'0 = p0 + d0
						p[0][i] += d0
						#q'0 = q0 - d0
						q[0][i] -= d0
						#p'1 = p1 + dp1
						p[1][i] += dp1
						#q'1 = q1 + dq1
						q[1][i] += dq1
						
	else: #cc == YUV_U or cc == YUV_V
		#Perform chroma deblocking
		c0 = QP_2_TC_TABLE[qp + 2] #qp + 2 due to boundary strength being 2.
		for i in range(4):
			#δc=(((p0−q0)≪2)+p1−q1+4)≫3
			dc_no_clip = (((p[0][i] - q[0][i]) << 2) + p[1][i] - q[1][i] + 4) >> 3
			dc = clip(-c0, c0, dc_no_clip)
			p[0][i] += dc
			q[0][i] -= dc
	
	#Set pixels to their new values
	if edge == VERT_EDGE:
		for i in range(4):
			for j in range(4):
				pix[q_pos[X] - i - 1, q_pos[Y] + j] = OverwriteTuple(pix[q_pos[X] - i - 1, q_pos[Y] + j], cc, clip(0, 255, p[i][j]))
				pix[q_pos[X] + i, q_pos[Y] + j] = OverwriteTuple(pix[q_pos[X] + i, q_pos[Y] + j], cc, clip(0, 255, q[i][j]))
	else: #edge == HORZ_EDGE
		for i in range(4):
			for j in range(4):
				pix[q_pos[X] + j, q_pos[Y] - i - 1] = OverwriteTuple(pix[q_pos[X] + j, q_pos[Y] - i - 1], cc, clip(0, 255, p[i][j]))
				pix[q_pos[X] + j, q_pos[Y] + i] = OverwriteTuple(pix[q_pos[X] + j, q_pos[Y] + i], cc, clip(0, 255, q[i][j]))
				
	return

#VERT EDGE DEBLOCKING:
#p30 p20 p10 p00 | q00 q10 q20 q30
#p31 p21 p11 p01 | q01 q11 q21 q31
#p32 p22 p12 p02 | q02 q12 q22 q32
#p33 p23 p13 p03 | q03 q13 q23 q33
#HORZ EDGE DEBLOCKING:
#p30 p31 p32 p33
#p20 p21 p22 p23
#p10 p11 p12 p13
#p00 p01 p02 p03
#---------------
#q00 q01 q02 q03
#q10 q11 q12 q13
#q20 q21 q22 q23
#q30 q31 q32 q33
#WHERE q00 refers to the pixel at the top-left position of the 4x4 block that we're looking at. 
def Deblock4x4(pix, q_pos, cc, edge):
	#My own deblocking algorithm, which may or may not be any good.
	
	#Initialize temporary pixel data
	p = [[0]*4 for i in range(4)]
	q = [[0]*4 for i in range(4)]
	if edge == VERT_EDGE:
		for i in range(4):
			for j in range(4):
				p[i][j] = pix[q_pos[X] - i - 1, q_pos[Y] + j][cc]
				q[i][j] = pix[q_pos[X] + i, q_pos[Y] + j][cc]
	else: #edge == HORZ_EDGE
		for i in range(4):
			for j in range(4):
				p[i][j] = pix[q_pos[X] + j, q_pos[Y] - i - 1][cc]
				q[i][j] = pix[q_pos[X] + j, q_pos[Y] + i][cc] 
	
	for i in range(4): #For every line in the 4x4 block.
		avg0 = (p[0][i] + q[0][i]) >> 1
		p[0][i] = (p[0][i] + avg0) >> 1
		q[0][i] = (q[0][i] + avg0) >> 1
		
		p_avg1 = (p[1][i] + p[0][i]) >> 1
		p[1][i] = (p[1][i] + p_avg1) >> 1
		q_avg1 = (q[1][i] + q[0][i]) >> 1
		q[1][i] = (q[1][i] + q_avg1) >> 1
		
		#p_avg2 = (p[2][i] + p[1][i]) >> 1
		#p[2][i] = (p[2][i] + p_avg2) >> 1
		#q_avg2 = (q[2][i] + q[1][i]) >> 1
		#q[2][i] = (q[2][i] + q_avg2) >> 1
		#
		#p_avg3 = (p[3][i] + p[2][i]) >> 1
		#p[3][i] = (p[3][i] + p_avg3) >> 1
		#q_avg3 = (q[3][i] + q[2][i]) >> 1
		#q[3][i] = (q[3][i] + q_avg3) >> 1
	
	#Set pixels to their new values
	if edge == VERT_EDGE:
		for i in range(4):
			for j in range(4):
				pix[q_pos[X] - i - 1, q_pos[Y] + j] = OverwriteTuple(pix[q_pos[X] - i - 1, q_pos[Y] + j], cc, clip(0, 255, p[i][j]))
				pix[q_pos[X] + i, q_pos[Y] + j] = OverwriteTuple(pix[q_pos[X] + i, q_pos[Y] + j], cc, clip(0, 255, q[i][j]))
	else: #edge == HORZ_EDGE
		for i in range(4):
			for j in range(4):
				pix[q_pos[X] + j, q_pos[Y] - i - 1] = OverwriteTuple(pix[q_pos[X] + j, q_pos[Y] - i - 1], cc, clip(0, 255, p[i][j]))
				pix[q_pos[X] + j, q_pos[Y] + i] = OverwriteTuple(pix[q_pos[X] + j, q_pos[Y] + i], cc, clip(0, 255, q[i][j]))
				
	return

def DeblockPicture(im, frame_size_tiles, tile_size_pix):
	#Smooth over pixel data between tile boundaries.
	#Loosely based off of HEVC Deblocking, as described on this IEEE site:
	#  https://ieeexplore.ieee.org/document/6324414/?reload=true
	
	if type(im) is not Image.Image or not IsValid2DSize(frame_size_tiles) or not IsValid2DSize(tile_size_pix):
		return None
		
	if tile_size_pix[X] % 8 is not 0 or tile_size_pix[Y] % 8 is not 0:
		Log(WARN, 'Deblocking is only enabled for pictures whose tile sizes are divisible by 8. Deblocking will be skipped.')
		return im
	
	#essentially a shallow pointer of pixel data
	pixels = im.load() 
	
	#NOTE 1: Boundary Strength (bs) for all edges must be 2, as the image is intra.
	#NOTE 2: Quantization Parameter (qp) is generally meaningless in this context.
	#  TODO: Add flag for qp, which applies for the entire image.
	bs = 2
	qp = 30 #A total guess. Technically this is the average QP between two 4x4 blocks.
	beta_offset_div2 = 0 #Also a total guess.
	tc_offset_div2 = 0 #also also a total guess.
	beta = QP_2_BETA_TABLE[clip(MIN_QP, MAX_QP, qp + (beta_offset_div2 << 1))]
	tc = QP_2_TC_TABLE[clip(MIN_QP, MAX_QP + 2, qp + 2 * (bs - 1) + (tc_offset_div2 << 1))]
	
	for tile_y in range(frame_size_tiles[Y]):
		for tile_x in range(frame_size_tiles[X]):
			tile_start_pos = (tile_x * tile_size_pix[X], tile_y * tile_size_pix[Y])
			tile_end_pos = (((tile_x + 1) * tile_size_pix[X]) - 1, ((tile_y + 1) * tile_size_pix[Y]) - 1)
			
			#Determine deblocking positions, which tend to be shifted 4 up and left.
			dblk_start_pos = (max(0, tile_start_pos[X] - 4), max(0, tile_start_pos[Y] - 4))
			dblk_end_pos_x = tile_end_pos[X] - 4
			if tile_x + 1 >= frame_size_tiles[X]:
				dblk_end_pos_x = frame_size_tiles[X] * tile_size_pix[X] - 1
			dblk_end_pos_y = tile_end_pos[Y] - 4
			if tile_y + 1 >= frame_size_tiles[Y]:
				dblk_end_pos_y = frame_size_tiles[Y] * tile_size_pix[Y] - 1
			dblk_end_pos = (dblk_end_pos_x, dblk_end_pos_y)
			
			#Perform deblocking on the 4x4 blocks within the "deblock tile"
			for dblk_pos_y in range(dblk_start_pos[Y], dblk_end_pos[Y], 4):
				for dblk_pos_x in range(dblk_start_pos[X], dblk_end_pos[X], 4):
					#If the left 4x4 block is not in the same tile as the current 4x4 block, 
					#perform vertical deblocking.
					if dblk_pos_x < tile_start_pos[X]:
						q_pos = (dblk_pos_x + 4, dblk_pos_y)
						for color_channel in range(3): #Y, U, V
							Deblock4x4(pixels, q_pos, color_channel, VERT_EDGE)
							#HEVCDeblock4x4(pixels, q_pos, beta, tc, color_channel, qp, VERT_EDGE)
					
					#If the above 4x4 block is not in the same tile as the current 4x4 block,
					#perform horizontal deblocking.
					if dblk_pos_y < tile_start_pos[Y]:
						q_pos = (dblk_pos_x, dblk_pos_y + 4)
						for color_channel in range(3): #Y, U, V
							Deblock4x4(pixels, q_pos, color_channel, HORZ_EDGE)
							#HEVCDeblock4x4(pixels, q_pos, beta, tc, color_channel, qp, HORZ_EDGE)
	
	return im
	
def ProcessTileGridNoCompare(tile_grid, tile_map, frame_width, frame_height):
	if tile_grid == []:
		return []
		
	#Fill tile grid from left to right, top to bottom.
	for i in range(frame_height):
		for j in range(frame_width):
			tile_grid[i][j] = random.choice(tile_grid[i][j])
	
	return tile_grid
	
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
				exp_bound[TOP] = [tile_map[tile_grid[i - 1][j]].boundaries[BOT]]
			if i < frame_height - 1 and tile_grid[i + 1][j] != []:
				exp_bound[BOT] = list(set(tile.boundaries[TOP] for tile in [tile_map[k] for k in tile_grid[i + 1][j]]))
			if j > 0 and tile_grid[i][j - 1] != []:
				exp_bound[LEFT] = [tile_map[tile_grid[i][j - 1]].boundaries[RIGHT]]
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
	
	propogate_error = False
	
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
		
		if tile_grid[y][x] == []:
			Log(ERR, 'Impossibility Pruning Loop removed ALL candidates from a grid space. Check your tile boundary possibilities.')
			break
			
	print('  Finished Pruning Impossibilities.')
	sys.stdout.flush()
	
	#Fill tile grid from left to right, top to bottom.
	for i in range(frame_height):
		for j in range(frame_width):
			if propogate_error:
				tile_grid[i][j] = []
				continue
				
			if i == 0 and j == 0 and len(tile_grid[i][j]) > 0:
				tile_grid[i][j] = random.choice(tile_grid[i][j])
				continue
				
			
			#Ignore tile spaces with [], as those are deemed invalid and we do not wish to propagate the error.
			exp_bound = {TOP:[], RIGHT:[], BOT:[], LEFT:[]}
			if i > 0 and tile_grid[i - 1][j] != []:
				exp_bound[TOP] = [tile_map[tile_grid[i - 1][j]].boundaries[BOT]]
			if i < frame_height - 1 and tile_grid[i + 1][j] != []:
				exp_bound[BOT] = list(set([tile.boundaries[TOP] for tile in [tile_map[k] for k in tile_grid[i + 1][j]]]))
			if j > 0 and tile_grid[i][j - 1] != []:
				exp_bound[LEFT] = [tile_map[tile_grid[i][j - 1]].boundaries[RIGHT]]
			if j < frame_width - 1 and tile_grid[i][j + 1] != []:
				exp_bound[RIGHT] = list(set([tile.boundaries[LEFT] for tile in [tile_map[k] for k in tile_grid[i][j + 1]]]))
			
			#Filter items from tile_map to match user's restrictions for this tile space
			restrict_tile_map = {k:v for k,v in tile_map.items() if k in tile_grid[i][j]}
			tile_cand_list = GetViableTiles(restrict_tile_map, exp_bound)

			if tile_cand_list != [] and i > 0 and j < frame_width - 1:
				#Need to also take into account the tile that was placed in the diagonally upper-right position
				#so that we don't choose a tile that will leave the grid space to the right without options
				exp_bound_right = {TOP:[], RIGHT:[], BOT:[], LEFT:[]}
				exp_bound_right[TOP] = [tile_map[tile_grid[i - 1][j + 1]].boundaries[BOT]]
				if i < frame_height - 1 and tile_grid[i + 1][j + 1] != []:
					exp_bound_right[BOT] = list(set([tile.boundaries[TOP] for tile in [tile_map[k] for k in tile_grid[i + 1][j + 1]]]))
				if j < frame_width - 2 and tile_grid[i][j + 2] != []:
					exp_bound_right[RIGHT] = list(set([tile.boundaries[LEFT] for tile in [tile_map[k] for k in tile_grid[i][j + 2]]]))

				right_tile_map = {k:v for k,v in tile_map.items() if k in tile_grid[i][j + 1]}
				
				indices_to_del = []
				for k, tile_cand in enumerate(tile_cand_list):
					exp_bound_right[LEFT] = [tile_map[tile_cand].boundaries[RIGHT]]
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
			is_viable &= tile.CompareBoundaries(dir, exp_bound[dir])
		
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
	
	print('Loading Images:')
	files_loaded = 0
	percent_done = 0.0
	for file in files:
		if not os.path.isfile(file):
			Log(WARN, 'Could not get image information from ' + file + '. File recursion not supported.')
			files_loaded += 1
			continue
		
		try:
			im = Image.open(file)
			im = im.convert('YCbCr') #Makes operations such as deblocking work.
			
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
	
		files_loaded += 1
		if (files_loaded / len(files))*100.0 >= percent_done + 10:
			percent_done = ((files_loaded * 10) // len(files)) * 10.0
			print('  ' + str(percent_done) + '% of images have been loaded.')
			sys.stdout.flush()
	
	if add_im:
		#Many of the images that we just added could be duplicates.
		#Remove duplicate images to reduce run time of further operations in the future.
		#Note: Normally would delete duplicates by having images be a set and avoid a function call, 
		#but that won't work here, as each image contains some file object member.
		print('  Deleting Duplicates')
		sys.stdout.flush()
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

def IsPosInt(x):
	return type(x) == int and x > 0

def IsValid2DSize(x):
	return type(x) == tuple and len(x) == 2 and IsPosInt(x[0]) and IsPosInt(x[1])
	
def Get2TupleFromStr(tuple_str):
	#allow for various ways of sending in frame size, including "1,1" and "(1,1)"
	tuple_str = re.sub('[(){}<>]', '', tuple_str)
	tuple_str_arr = re.split('\s|,|x|X', tuple_str)
	tuple_str_arr = list(filter(None, tuple_str_arr))
	
	int_arr = []
	for tuple_str_i in tuple_str_arr:
		int_str = ''.join(filter(lambda x: x.isdigit(), tuple_str_i))
		
		if int_str == '':
			Log(ERR, 'Could not retrieve integer from ' + tuple_str_i + ' from "' + tuple_str + '"')
			int_str = '0'	
		
		int_arr.append(int(int_str))
		
	tuple_arr = tuple(int_arr)
	if not IsValid2DSize(tuple_arr):
		Log(ERR, 'tile size provided was "' + tuple_str + '", which is not a 2-tuple')
		tuple_arr = (0,0)
		
	return tuple_arr

def CloseImages(im_list):
	for im in im_list:
		im.close()

def Main():
	global g_err_occurred
	args = ParseCommandLineArgs()
	
	SetupLogging(args.log)
	
	(frame_width, frame_height) = (-1, -1)
	tile_grid = []
	
	im_list = GetImagesFromPath(args.path, args.add_im)
	tile_map = GetTilesFromImages(im_list)
	if not g_err_occurred:
		print('Tiles have been created.\nCreating Tile Grid.')
		sys.stdout.flush()
	
	if args.grid == '':
		(frame_width, frame_height) = Get2TupleFromStr(args.size)
		tile_grid = ConstructTileGrid(tile_map, frame_width, frame_height)
	else:
		grid_path = os.path.join(args.path, args.grid)
		(tile_grid, frame_width, frame_height) = GetTileGridFromFile(grid_path, tile_map)
	
	if not g_err_occurred:
		print('Created Tile Grid.\nProcessing Tile Grid.')
		sys.stdout.flush()
	
	if args.speed_mode == NORMAL:
		tile_grid = ProcessTileGrid(tile_grid, tile_map, frame_width, frame_height)
	elif args.speed_mode == FAST:
		tile_grid = FastProcessTileGrid(tile_grid, tile_map, frame_width, frame_height)
	elif args.speed_mode == NO_COMPARE:
		tile_grid = ProcessTileGridNoCompare(tile_grid, tile_map, frame_width, frame_height)
	else:
		Log(ERR, 'speed_mode "' + str(args.speed_mode) + '" does not exist')
		tile_grid = []
	
	if not g_err_occurred:
		print('Processing has finished. Creating picture')
		sys.stdout.flush()
	new_im = CreatePictureFromTileGrid(tile_grid, tile_map, frame_width, frame_height)
	
	if args.speed_mode == NO_COMPARE and not g_err_occurred:
		print('Deblocking the created picture.')
		new_im = DeblockPicture(new_im, (frame_width, frame_height), im_list[0].size)
	
	if type(new_im) == Image.Image:
		new_im.save(args.out)
	
	CloseImages(im_list)
	CloseLog()
	
	if not g_err_occurred:
		print('DONE')
	
if __name__ == "__main__":
	Main()