#!/usr/bin/python3.5
from ctypes import *
import math
import face_recognition
import random
import argparse
import cv2
import time
import rospy
import pickle
from std_msgs.msg import String

fpsLimit = 3
startTime = time.time()

#argument parser to get input video files
ap = argparse.ArgumentParser()
ap.add_argument("-i", "--input", required=True,
	help="path to input video")
ap.add_argument("-o", "--output", type=str,
	help="path to output video")
args = vars(ap.parse_args())
stream = cv2.VideoCapture(args["input"])
writer = None

def talker(hello_str):
	pub = rospy.Publisher('chatter', String, queue_size=100)
	rospy.init_node('talker', anonymous=True)
	rate = rospy.Rate(10) # 10hz
	while not rospy.is_shutdown():
		hello_str = hello_str #+ rospy.get_time()
		rospy.loginfo(hello_str)
		pub.publish(hello_str)
		rate.sleep()

def crop_face(image, px, py, pw, ph):
	crop_image = image[py:py+ph, px:px+pw]
	some_flag = True
	return some_flag, crop_image

def sample(probs):
	s = sum(probs)
	probs = [a/s for a in probs]
	r = random.uniform(0, 1)
	for i in range(len(probs)):
		r = r - probs[i]
		if r <= 0:
			return i
	return len(probs)-1

def c_array(ctype, values):
	arr = (ctype*len(values))()
	arr[:] = values
	return arr

class BOX(Structure):
	_fields_ = [("x", c_float),
				("y", c_float),
				("w", c_float),
				("h", c_float)]

class DETECTION(Structure):
	_fields_ = [("bbox", BOX),
				("classes", c_int),
				("prob", POINTER(c_float)),
				("mask", POINTER(c_float)),
				("objectness", c_float),
				("sort_class", c_int)]


class IMAGE(Structure):
	_fields_ = [("w", c_int),
				("h", c_int),
				("c", c_int),
				("data", POINTER(c_float))]

class METADATA(Structure):
	_fields_ = [("classes", c_int),
				("names", POINTER(c_char_p))]

	

lib = CDLL("/home/nvidia/darknet/libdarknet.so", RTLD_GLOBAL) ##replace it with path in pc
#lib = CDLL("libdarknet.so", RTLD_GLOBAL)
lib.network_width.argtypes = [c_void_p]
lib.network_width.restype = c_int
lib.network_height.argtypes = [c_void_p]
lib.network_height.restype = c_int

predict = lib.network_predict
predict.argtypes = [c_void_p, POINTER(c_float)]
predict.restype = POINTER(c_float)

set_gpu = lib.cuda_set_device
set_gpu.argtypes = [c_int]

make_image = lib.make_image
make_image.argtypes = [c_int, c_int, c_int]
make_image.restype = IMAGE

get_network_boxes = lib.get_network_boxes
get_network_boxes.argtypes = [c_void_p, c_int, c_int, c_float, c_float, POINTER(c_int), c_int, POINTER(c_int)]
get_network_boxes.restype = POINTER(DETECTION)

make_network_boxes = lib.make_network_boxes
make_network_boxes.argtypes = [c_void_p]
make_network_boxes.restype = POINTER(DETECTION)

free_detections = lib.free_detections
free_detections.argtypes = [POINTER(DETECTION), c_int]

free_ptrs = lib.free_ptrs
free_ptrs.argtypes = [POINTER(c_void_p), c_int]

network_predict = lib.network_predict
network_predict.argtypes = [c_void_p, POINTER(c_float)]

reset_rnn = lib.reset_rnn
reset_rnn.argtypes = [c_void_p]

load_net = lib.load_network
load_net.argtypes = [c_char_p, c_char_p, c_int]
load_net.restype = c_void_p

do_nms_obj = lib.do_nms_obj
do_nms_obj.argtypes = [POINTER(DETECTION), c_int, c_int, c_float]

do_nms_sort = lib.do_nms_sort
do_nms_sort.argtypes = [POINTER(DETECTION), c_int, c_int, c_float]

free_image = lib.free_image
free_image.argtypes = [IMAGE]

letterbox_image = lib.letterbox_image
letterbox_image.argtypes = [IMAGE, c_int, c_int]
letterbox_image.restype = IMAGE

load_meta = lib.get_metadata
lib.get_metadata.argtypes = [c_char_p]
lib.get_metadata.restype = METADATA

load_image = lib.load_image_color
load_image.argtypes = [c_char_p, c_int, c_int]
load_image.restype = IMAGE

rgbgr_image = lib.rgbgr_image
rgbgr_image.argtypes = [IMAGE]

predict_image = lib.network_predict_image
predict_image.argtypes = [c_void_p, IMAGE]
predict_image.restype = POINTER(c_float)

def classify(net, meta, im):
	out = predict_image(net, im)
	res = []
	for i in range(meta.classes):
		res.append((meta.names[i], out[i]))
	res = sorted(res, key=lambda x: -x[1])
	return res

def detect(net, meta, image, thresh=.5, hier_thresh=.5, nms=.45):
	im = load_image(image, 0, 0)
	num = c_int(0)
	pnum = pointer(num)
	predict_image(net, im)
	dets = get_network_boxes(net, im.w, im.h, thresh, hier_thresh, None, 0, pnum)
	num = pnum[0]
	flag = 0
	if (nms): do_nms_obj(dets, num, meta.classes, nms);
	res = []
	for j in range(num):
		for i in range(meta.classes):
			if dets[j].prob[i] > 0:
				b = dets[j].bbox
				flag = 1
				
				res.append((meta.names[i], dets[j].prob[i], (b.x, b.y, b.w, b.h)))
	res = sorted(res, key=lambda x: -x[1])
	free_image(im)
	free_detections(dets, num)
	return res
def output(image, net, meta, re):			#define names clearly
	cv2.imwrite("predict.jpg", image)
	r = detect(net, meta, b"predict.jpg")
		#print(r[0][0])
		#print(len(r))
	#talker(r)
	#else:
		#print("Fuck you")
	if re == []:
		print("nothing detected")
	else:
		new_list = []
		new_list = re[2]
		px = (int)(new_list[0])			## px and py are the centre of the detection
		py = (int)(new_list[1])
		pw = (int)(new_list[2])			## pw and ph are width and height of the detection
		ph = (int)(new_list[3])
		p_x = (int)((2*px-pw)/2)
		p_y = (int)((2*py-ph)/2)
		name = re[0].decode("utf-8")
		#talker(name)
		if r != []:
					l = len(r)
					for x in range(l):
				#crop_image(image, p_x, p_y, pw, ph)
							object_rec = r[x][0].decode("utf-8")
							if object_rec == 'person':
									some_flag,c_image = crop_face(image, p_x, p_y, pw, ph)
									cv2.imshow("cropped", c_image)
									cv2.waitKey(1)
					print("recognised a person")
				#print(r[0][0])
				#print(len(r))

		image = cv2.rectangle(image,(p_x,p_y),(p_x+pw,p_y+ph),(0,255,0),3)   #(p_x+pw,p_y+ph) is opposite vertex of (p_x,p_y)
		p = p_y - 15 if p_y - 15 > 15 else p_y + 15
		cv2.putText(image, name, (px, p), cv2.FONT_HERSHEY_SIMPLEX, 0.75, (0, 255, 0), 2)
	return image, re



path1 = b"/home/nvidia/darknet/cfg/yolov3.cfg"  ##replace these with paths in pc
path2 =  b"/home/nvidia/darknet/yolov3.weights"
if __name__ == "__main__":
	#net = load_net("cfg/densenet201.cfg", "/home/pjreddie/trained/densenet201.weights", 0)
	#im = load_image("data/wolf.jpg", 0, 0)
	#meta = load_meta("cfg/imagenet1k.data")
	#r = classify(net, meta, im)
	#print r[:10]
	print("[INFO] loading encodings...")
	data = pickle.loads(open('encodings.pickle', "rb").read())

	net = load_net(path1,path2, 0)
	meta = load_meta(b"/home/nvidia/darknet/cfg/coco.data")

	while(True):
		ret,image = stream.read()
		if not ret:
			break
		nowTime = time.time()
		time_elasped = nowTime - startTime
		if time_elasped > 1./fpsLimit:
			some_flag = False
			cv2.imwrite("predict.jpg", image)
			r = detect(net, meta, b"predict.jpg")
			#talker()
			if r == []:
				print()
			else:
				for re in r:
					image, name = output(image, net, meta, re)
			if writer is None and args["output"] is not None:
				fourcc = cv2.VideoWriter_fourcc(*"MJPG")
				writer = cv2.VideoWriter(args["output"], fourcc, 24,  (image.shape[1], image.shape[0]), True)
			#talker(name)
			if some_flag == True:	
				rgb = cv2.cvtColor(c_image, cv2.COLOR_BGR2RGB)
				rgb = imutils.resize(c_image, width=750)
				r = c_image.shape[1] / float(rgb.shape[1])
				boxes = face_recognition.face_locations(rgb,
					model=args["detection_method"])
				encodings = face_recognition.face_encodings(rgb, boxes)
				names = []

	# loop over the facial embeddings
				for encoding in encodings:
		# attempt to match each face in the input image to our known
		# encodings
					matches = face_recognition.compare_faces(data["encodings"],
						encoding)
					name = "Unknown"

		# check to see if we have found a match
					if True in matches:
			# find the indexes of all matched faces then initialize a
			# dictionary to count the total number of times each face
			# was matched
						matchedIdxs = [i for (i, b) in enumerate(matches) if b]
						counts = {}

			# loop over the matched indexes and maintain a count for
			# each recognized face face
						for i in matchedIdxs:
							name = data["names"][i]
							counts[name] = counts.get(name, 0) + 1

			# determine the recognized face with the largest number
			# of votes (note: in the event of an unlikely tie Python
			# will select first entry in the dictionary)
						name = max(counts, key=counts.get)
		
		# update the list of names
					names.append(name)
			print(name)
			#if writer is not None:
				#writer.write(image)
	
#			cv2.imshow("image", image)
		startTime = time.time()
		cv2.waitKey(1)

