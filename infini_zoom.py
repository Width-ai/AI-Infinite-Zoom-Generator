from pathlib import Path
from exceptions.argument_exception import ArgumentException
from detectors.template_detector import *

import helper.image_helper as ih
import cv2
import math


class InfiniZoomParameter:
    def __init__(self):
        self.__zoom_steps = 100
        self.__reverse = False
        self.__auto_sort = False
        self.__zoom_image_crop = 0.8
        self.zoom_factor = 2

    @property
    def zoom_factor(self):
        return self.__zoom_factor
    
    @zoom_factor.setter
    def zoom_factor(self, f: float):
        self.__zoom_factor = f

    @property
    def zoom_image_crop(self):
        return self.__zoom_image_crop
    
    @zoom_image_crop.setter
    def zoom_image_crop(self, crop: float):
        self.__zoom_image_crop = crop

    @property
    def reverse(self):
        return self.__reverse
    
    @reverse.setter
    def reverse(self, stat: bool):
        self.__reverse = stat

    @property
    def auto_sort(self):
        return self.__auto_sort
    
    @auto_sort.setter
    def auto_sort(self, stat: bool):
        self.__auto_sort = stat

    @property
    def zoom_steps(self):
        return self.__zoom_steps
    
    @zoom_steps.setter
    def zoom_steps(self, steps: int):
        if steps<1:
            raise ArgumentException("Range error: steps must be greater than 0")
        
        self.__zoom_steps = steps

    @property
    def input_path(self):
        return self.__input_path
    
    @input_path.setter
    def input_path(self, path : Path):
        self.__input_path = path        

    @property
    def output_file(self):
        return self.__output_file
    
    @output_file.setter
    def output_file(self, file):
        self.__output_file = file


class InfiniZoom:
    def __init__(self, param : InfiniZoomParameter):
        self.__param = param
        self.__image_list = []
        self.__video_writer = None


    def __load_images(self):
        if not self.__param.input_path.exists():
            raise Exception("input path does not exist")
        
        print(f'\nReading images from "{str(self.__param.input_path)}"')
        self.__image_list = ih.read_images_folder(self.__param.input_path)
        print(f' - {len(self.__image_list)} images read\n')


    def __print_matrix(self, matrix):
        rows, cols = matrix.shape
        for i in range(rows):
            for j in range(cols):
                if matrix[i, j]==0:
                    print(' -- ', end=" ")  # Print element followed by a tab    
                else:
                    print(f'{matrix[i, j]:.2f}', end=" ")  # Print element followed by a tab

            print()

    def __merge_images_horizontally(self,image1, image2, image3, scale=0.5):
        # Check if the input images have the same size
        if image1.shape != image2.shape or image1.shape != image3.shape:
            raise ValueError("Input images must have the same size.")

        # Downscale the images
        scaled_image1 = cv2.resize(image1, None, fx=scale, fy=scale)
        scaled_image2 = cv2.resize(image2, None, fx=scale, fy=scale)
        scaled_image3 = cv2.resize(image3, None, fx=scale, fy=scale)

        # Create a new blank image with triple width
        merged_width = int(scaled_image1.shape[1] + scaled_image2.shape[1] + scaled_image3.shape[1])
        merged_height = min(scaled_image1.shape[0], scaled_image2.shape[0], scaled_image3.shape[0])
        merged_image = np.zeros((merged_height, merged_width, 3), dtype=np.uint8)

        # Stack the images horizontally
        merged_image[:, :scaled_image1.shape[1]] = scaled_image1
        merged_image[:, scaled_image1.shape[1]:scaled_image1.shape[1]+scaled_image2.shape[1]] = scaled_image2
        merged_image[:, scaled_image1.shape[1]+scaled_image2.shape[1]:] = scaled_image3

        return merged_image

    def __auto_sort(self):
        print(f'Determining image order')

        detector = TemplateDetector(threshold=0.01, max_num=1)

        print(f' - matching images')

        num = len(self.__image_list)
        scores = np.zeros((num, num))
        for i in range(0, num):
            for j in range(0, num):
                if i==j:
                    continue
                
                img1 = self.__image_list[i].copy()
                img2 = self.__image_list[j].copy()
                if img1.shape != img2.shape:
                    raise Exception("Auto sort failed: Inconsistent image sizes!")
                
                h, w = img1.shape[:2]

                mtx_scale = cv2.getRotationMatrix2D((0, 0), 0, 1/self.__param.zoom_factor)
                img2 = cv2.warpAffine(img2, mtx_scale, (int(w*1/self.__param.zoom_factor), int(h*1/self.__param.zoom_factor)))

                detector.pattern = img2
                result, result_img = detector.search(img1)

#                img22 = cv2.copyMakeBorder(img2, 0, h-img2.shape[0], 0, w-img2.shape[1], cv2.BORDER_CONSTANT, value=[0,0,0])
#                merge = self.__merge_images_horizontally(self.__image_list[i], img22, img22)
#                cv2.imshow("Image", merge)
#                cv2.waitKey()

                if len(result)==0:
                    print(f'Correlating image {i} with image {j}: images are uncorrelated.')
                    continue
                else:                    
                    bx, by, bw, bh, score = result[0, :5]

                scores[i, j] = score
                print(f'.', end='')

        # process the data to find the best matches for each image        
        self.__image_list = self.__filter_array(scores)


    def __filter_array(self, arr):
        filtered = np.zeros(arr.shape)

        # Get the indices of the row and column maxima
        row_max_indices = np.argmax(arr, axis=1)
        col_max_indices = np.argmax(arr, axis=0)

        # We need to find the first image of the series now. To do this we must check the
        # images that could not be matched as a follow up image to any of the images.
        # This could be images that were added accidentally but the first image is also unlinked!
        unlinked_images = []
        for r in range(arr.shape[0]):
            # index of the maximum value of row r
            col_max = row_max_indices[r]

            # is this also the column maximum?
            if col_max_indices[col_max]==r:
                filtered[r, col_max] = arr[r, col_max]
            else:
                unlinked_images.append(r)

        # Print the image connection matrix
        print(f'\n\nImage relation matrix:')
        self.__print_matrix(filtered)

        # Now eliminate all unlinked images and find the first one:
        num_unlinked = len(unlinked_images)
        print(f' - found {num_unlinked} unlinked images.')
        if num_unlinked>1:
            print(f' - Warning: Your series contains {num_unlinked-1} images that cannot be matched!')

        print('\nFinding first image:')
        start_candidates = []
        for i in range(0, len(unlinked_images)):
            idx = unlinked_images[i]
            col = filtered[:, idx]
            if np.any(col != 0):
                print(f' - Image {idx} is the start of a zoom series')
                start_candidates.append(idx)
            else:
                print(f' - Discarding image {idx} because it is unconnected to other images!')

        if len(start_candidates)==0:
            raise("Aborting: Could not find start image!")

        if len(start_candidates)>1:
            raise(f'Aborting: Clean up image series! Found {len(start_candidates)} different images that could be the starting image!')

        # finally build sorted image list
        sequence_order = self.__assemble_image_sequence(idx, filtered)
        print(f' - Image sequence is {",".join(map(str, sequence_order))}')

        sorted_image_list = []
        for idx in sequence_order:
            sorted_image_list.append(self.__image_list[idx])
            
        return sorted_image_list


    def __assemble_image_sequence(self, start : int, conn_matrix):
        series = []

        next_image_index = start
        series.insert(0, next_image_index)

        non_zeros = np.nonzero(conn_matrix[:, next_image_index])[0]
        while len(non_zeros)>0:
            next_image_index = non_zeros[0]
            series.insert(0, next_image_index)

            non_zeros = np.nonzero(conn_matrix[:, next_image_index])[0]            

        return series
    

    def process(self):
        self.__load_images()

        if len(self.__image_list)==0:
            raise Exception("Processing failed: Image list is empty!")

        if self.__param.auto_sort:
            self.__auto_sort()

        h, w = self.__image_list[0].shape[:2]

        video_w = int(w * self.__param.zoom_image_crop)
        video_h = int(h * self.__param.zoom_image_crop)
        self.__video_writer = cv2.VideoWriter(self.__param.output_file, cv2.VideoWriter_fourcc(*'mp4v'), 60, (video_w, video_h))

        print(f'Generating Zoom Sequence')
        for i in range(len(self.__image_list)-1):
            img1 = self.__image_list[i]
            img2 = self.__image_list[i+1]

            self.zoom_in(self.__video_writer, img1, img2, video_w, video_h)

        cv2.destroyAllWindows()
        self.__video_writer.release()


    def zoom_in(self, video_writer, imgCurr, imgNext, video_w, video_h):
        steps = self.__param.zoom_steps

        # imgNext has exactly a quarter the size of img
        h, w = imgCurr.shape[:2]
        cx = w // 2
        cy = h // 2

        # compute step size for each partial image zoom. Zooming is an exponential
        # process, so we need to compute the steps on a logarithmic scale.
        step_size_log = math.exp(math.log(self.__param.zoom_factor)/steps)

        zf = 1
        img_curr = imgCurr.copy()
        img_next = imgNext.copy()

        for i in range(0, steps):
            zf = step_size_log**i
            
            mtx_curr = cv2.getRotationMatrix2D((cx, cy), 0, zf)
            img_curr = cv2.warpAffine(imgCurr, mtx_curr, (w, h))

            ww = round(w * (zf/2.0))
            hh = round(h * (zf/2.0))
            mtx_next = cv2.getRotationMatrix2D((cx, cy), 0, zf/2.0)

            img_next = imgNext.copy()
            img_next = cv2.warpAffine(img_next, mtx_next, (w, h))

            # Before copying throw away 25% of the outter image
            ww = int(ww*0.8)
            hh = int(hh*0.8)
            img_next = ih.crop_image(img_next, (ww, hh))

            if i == 0:
                # The second image may not be perfectly centered. We need to determine 
                # image offset to compensate
                detector = TemplateDetector(threshold=0.3, max_num=1)
                detector.pattern = img_next
                result, result_image = detector.search(img_curr)
                if len(result)==0:
                    raise Exception("Cannot match image to precursor!")

                bx, by, bw, bh, score = result[0, :5]
            
                # compute initial misalignment of the second image. Ideally the second image 
                # should be centered. We have to gradually eliminate the misalignment in the
                # successive zoom steps so that it is zero when switching to the next image.
                ma_x = int(cx - bx)
                ma_y = int(cy - by)
                print(f' - image misalignment: x={ma_x:.2f}; y={ma_y:.2f}')
                
                # Plausibility check. If the misalignment is too large something is wrong. Usually
                # the images are not in sequence.
                if math.sqrt(ma_x*ma_x + ma_y*ma_y) > 60:
                    img_small = cv2.copyMakeBorder(img_next, 0, h - hh, 0, w - ww, cv2.BORDER_CONSTANT, value=[0,0,0])
                    image_debug = self.__merge_images_horizontally(img_curr, img_small, img_small)

#                    cv2.imshow("Image", image_debug)
#                    cv2.waitKey()

                    raise Exception('Images are not properly aligned! Did you sort them correctly?')

                # How much do we need to compensate for each step?
                ma_comp_x = ma_x / steps
                ma_comp_y = ma_y / steps

            # Add the smaller image into the larger one but shift it to 
            # compensate the misalignment. Problem is that when it is maximized
            # it would be shifted off center. We need to fix that later.
            hs = hh//2 + int(ma_y)
            ws = ww//2 + int(ma_x)
            img_curr[cy-hs:cy-hs+hh, cx-ws:cx-ws+ww] = img_next

            #opacity = max(0, min(zf-1, 1))
            #img_curr = ih.overlay_images(img_curr, img_next, (int(-ma_x), int(-ma_y)), 'center', opacity)

            # finally we have to gradually shift the resulting image back because the
            # next frame should again be close to the center and the misalignment compensation
            # brought us away. So we gradually shift the combined image back so that the center
            # position remains in the center.
            ox = ma_comp_x * i
            oy = ma_comp_y * i
            mtx_shift = np.float32([[1, 0, ox], [0, 1, oy]])
            img_curr = cv2.warpAffine(img_curr, mtx_shift, (img_curr.shape[1], img_curr.shape[0]))

#            cv2.rectangle(img_curr, (int(bx-bw//2), int(by-bh//2)), (int(bx+bw//2), int(by+bh//2)), (0,0,255), 1)

            #print(f'bx={bx:.2f}; by={by:.2f}; score={score:.2f}; zoom={zf}; s1={ww}x{hh}; s2={h}x{w}')

            # final crop, ther may be some inconsiostencies at the boundaries
            img_curr = ih.crop_image(img_curr, (video_w, video_h))

            video_writer.write(img_curr)
            cv2.imshow("Image", img_curr)
            cv2.waitKey(10)



