import numpy as np
from PIL import Image
from skimage.color import rgb2hsv

from module.base.utils import color_similarity_2d
from module.template.assets import *


class GridPredictor:
    ENEMY_SCALE_IMAGE_SIZE = (50, 50)
    ENEMY_PERSPECTIVE_IMAGE_SIZE = (50, 50)

    def __init__(self, location, image, corner):
        """

        Args:
            location:
            image:
            corner:
        """
        self.location = location
        self.image = image
        self.corner = corner.flatten()

        x0, y0, x1, y1, x2, y2, x3, y3 = self.corner
        divisor = x0 - x1 + x2 - x3
        x = (x0 * x2 - x1 * x3) / divisor
        y = (x0 * y2 - x1 * y2 + x2 * y0 - x3 * y0) / divisor
        self._image_center = np.array([x, y, x, y])
        self._image_a = (-x0 * x2 + x0 * x3 + x1 * x2 - x1 * x3) / divisor
        self._perspective = (
            (-x0 + x1) / self.ENEMY_PERSPECTIVE_IMAGE_SIZE[0],  # a
            (-x0 * x3 + x1 * x2) / (-x2 + x3) / self.ENEMY_PERSPECTIVE_IMAGE_SIZE[1],  # b
            x0,  # c
            0,  # d
            (-x0 * y2 + x1 * y2 + x2 * y0 - x3 * y0) / (-x2 + x3) / self.ENEMY_PERSPECTIVE_IMAGE_SIZE[1],  # e
            y0,  # f
            0,  # g
            ((-x0 + x1) / (-x2 + x3) - 1) / self.ENEMY_PERSPECTIVE_IMAGE_SIZE[1]  # h
        )
        self.image_transform = self.image.transform(self.ENEMY_PERSPECTIVE_IMAGE_SIZE, Image.PERSPECTIVE, self._perspective)

    def predict(self):
        # self.image_hole = self.get_relative_image((-1, -1, 1, 1))
        self.is_enemy = self.predict_static_red_border()

        self.enemy_scale = self.predict_enemy_scale()
        if self.enemy_scale > 0:
            self.is_enemy = True
        self.is_mystery = self.predict_mystery()
        if not self.is_enemy and not self.is_mystery:
            self.is_siren = self.predict_dynamic_red_border()
        self.is_fleet = self.predict_fleet()
        if self.is_fleet:
            self.is_current_fleet = self.predict_current_fleet()
        self.is_boss = self.predict_boss()
        # self.image_perspective = color_similarity_2d(
        #     self.image.transform(self.ENEMY_PERSPECTIVE_IMAGE_SIZE, Image.PERSPECTIVE, self._perspective)
        #     , color=(255, 36, 82)
        # )

    def get_relative_image(self, relative_location, output_shape=None):
        """

        Args:
            relative_location(tuple): upper_left_x, upper_left_y, bottom_right_x, bottom_right_y
                (-1, -1, 1, 1)
            output_shape(tuple): (x, y)

        Returns:
            PIL.Image.Image
        """
        area = self._image_center + np.array(relative_location) * self._image_a
        area = tuple(np.rint(area).astype(int))
        image = self.image.crop(area)
        if output_shape is not None:
            image = image.resize(output_shape)
        return image

    def predict_enemy_scale(self):
        """
        icon on the upperleft which shows enemy scale: Large Middle Small.

        Returns:
            int: 1: Small, 2: Middle, 3: Large.
        """
        # if not self.is_enemy:
        #     return 0

        image = self.get_relative_image((-0.415 - 0.7, -0.62 - 0.7, -0.415, -0.62))
        image = np.stack(
            [
                color_similarity_2d(image, (255, 130, 132)),
                color_similarity_2d(image, (255, 239, 148)),
                color_similarity_2d(image, (255, 235, 156))
            ], axis=2
        )
        image = Image.fromarray(image).resize(self.ENEMY_SCALE_IMAGE_SIZE)

        if TEMPLATE_ENEMY_L.match(image):
            scale = 3
        elif TEMPLATE_ENEMY_M.match(image):
            scale = 2
        elif TEMPLATE_ENEMY_S.match(image):
            scale = 1
        else:
            scale = 0

        return scale

    def predict_static_red_border(self):
        # image = self.image.transform(self.ENEMY_PERSPECTIVE_IMAGE_SIZE, Image.PERSPECTIVE, self._perspective)

        image = color_similarity_2d(self.image_transform, color=(255, 36, 82))

        # Image.fromarray(np.array(image).astype('uint8'), mode='RGB').save(f'{self}.png')

        count = np.sum(image > 221)
        return count > 40

    def predict_dynamic_red_border(self, pad=4):
        image = np.array(self.image_transform).astype(float)
        r, b = image[:, :, 0], image[:, :, 2]
        image = r - b
        image[image < 0] = 0
        image[image > 255] = 255

        mask = np.ones(np.array(image.shape) - pad * 2) * -1
        mask = np.pad(mask, ((pad, pad), (pad, pad)), mode='constant', constant_values=1)
        image = image * mask
        image[r < 221] = 0
        # print(self, np.mean(image))
        return np.mean(image) > 2

    def screen_point_to_grid_location(self, point):
        a, b, c, d, e, f, g, h = self._perspective
        y = (point[1] - f) / (e - point[1] * h)
        x = (point[0] * (h * y + 1) - b * y - c) / a
        res = np.array((x, y)) / self.ENEMY_PERSPECTIVE_IMAGE_SIZE
        return res

    def _relative_image_color_count(self, area, color, output_shape=(50, 50), color_threshold=221):
        image = self.get_relative_image(area, output_shape=output_shape)
        image = color_similarity_2d(image, color=color)
        count = np.sum(image > color_threshold)
        return count

    def _relative_image_color_hue_count(self, area, h, s=None, v=None, output_shape=(50, 50)):
        image = self.get_relative_image(area, output_shape=output_shape)
        hsv = rgb2hsv(np.array(image) / 255)
        hue = hsv[:, :, 0]
        h = np.array([-1, 1]) + h
        count = (h[0] / 360 < hue) & (hue < h[1] / 360)
        if s:
            s = np.array([-1, 1]) + s
            saturation = hsv[:, :, 1]
            count &= (s[0] / 100 < saturation) & (saturation < s[1] / 100)
        if v:
            v = np.array([-1, 1]) + v
            value = hsv[:, :, 2]
            count &= (v[0] / 100 < value) & (value < v[1] / 100)

        count = np.sum(count)
        return count

    def predict_mystery(self):
        # if not self.may_mystery:
        #     return False
        # cyan question mark
        if self._relative_image_color_count(
                area=(-0.3, -2, 0.3, -0.6), color=(148, 255, 247), output_shape=(20, 50)) > 50:
            return True
        # white background
        # if self._relative_image_color_count(
        #         area=(-0.7, -1.7, 0.7, -0.3), color=(239, 239, 239), output_shape=(50, 50)) > 700:
        #     return True

        return False

    def predict_fleet(self):
        # white ammo icon
        # return self._relative_image_color_count(
        #     area=(-1, -2, -0.5, -1.5), color=(255, 255, 255), color_threshold=252) > 300
        # count = self._relative_image_color_hue_count(area=(-1, -2, -0.5, -1.5), h=(0, 360), s=(0, 5), v=(95, 100))
        # return count > 300
        image = self.get_relative_image((-1, -2, -0.5, -1.5), output_shape=self.ENEMY_SCALE_IMAGE_SIZE)
        image = color_similarity_2d(image, (255, 255, 255))
        return TEMPLATE_FLEET_AMMO.match(image)

    def predict_current_fleet(self):
        # Green arrow over head with hue around 141.
        # image = self.get_relative_image((-0.5, -3.5, 0.5, -2.5))
        # hue = rgb2hsv(np.array(image) / 255)[:, :, 0] * 360
        # count = np.sum((141 - 3 < hue) & (hue < 141 + 3))
        # return count > 1000
        count = self._relative_image_color_hue_count(
                area=(-0.5, -3.5, 0.5, -2.5), h=(141 - 3, 141 + 10), output_shape=(50, 50))
        return count > 600

    def predict_boss(self):
        # count = self._relative_image_color_count(
        #     area=(-0.55, -0.2, 0.45, 0.2), color=(255, 77, 82), color_threshold=247)
        # return count > 100

        if TEMPLATE_ENEMY_BOSS.match(
                self.get_relative_image((-0.55, -0.2, 0.45, 0.2), output_shape=(50, 20)),
                similarity=0.75):
            return True

        # 微层混合 event_20200326_cn
        if self._relative_image_color_hue_count(
                area=(0.13, -0.05, 0.63, 0.15), h=(358 - 3, 358 + 3), v=(96, 100), output_shape=(50, 20)) > 100:
            if TEMPLATE_ENEMY_BOSS.match(
                    self.get_relative_image((0.13, -0.05, 0.63, 0.15), output_shape=(50, 20)), similarity=0.4):
                return True

        return False