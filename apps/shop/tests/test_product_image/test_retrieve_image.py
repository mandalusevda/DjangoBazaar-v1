import os

from django.urls import reverse
from rest_framework import status

from apps.shop.demo.factory.product.product_factory import ProductFactory
from apps.shop.models import ProductMedia
from apps.shop.tests.test_product.base_test_case import ProductBaseTestCase
from config import settings


class RetrieveImageTest(ProductBaseTestCase):
    files: list

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.active_product = ProductFactory.create_product(has_images=True)
        cls.active_product2 = ProductFactory.create_product(has_images=True)

    def setUp(self):
        self.set_admin_user_authorization()

    def test_retrieve_with_one_image(self):
        # request
        response = self.client.get(
            reverse(
                "product-images-list", kwargs={"product_pk": self.active_product.id}
            ),
        )

        # expected
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = response.json()
        image = expected[0]
        self.assertIsInstance(expected, list)
        self.assertEqual(len(expected), 1)

        self.assertIsInstance(image["id"], int)
        self.assertEqual(image["product_id"], self.active_product.id)
        self.assertTrue(image["src"].strip())
        self.assertIsNone(image["alt"])
        self.assertDatetimeFormat(image["created_at"])
        self.assertDatetimeFormat(image["updated_at"])

        # check the fie was saved
        file_path = os.path.abspath(
            str(settings.MEDIA_ROOT) + image["src"].split("media")[1]
        )
        self.assertTrue(os.path.exists(file_path))

        # Check if the images have been added to the product
        product_media = ProductMedia.objects.filter(product=self.active_product)
        self.assertEqual(product_media.count(), 1)

    def test_retrieve_with_multi_images(self):
        # request
        response = self.client.get(
            reverse(
                "product-images-list", kwargs={"product_pk": self.active_product2.id}
            ),
        )

        # expected
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = response.json()
        self.assertIsInstance(expected, list)
        self.assertEqual(len(expected), 8)

        for image in expected:
            self.assertIsInstance(image["id"], int)
            self.assertEqual(image["product_id"], self.active_product2.id)
            self.assertTrue(image["src"].strip())
            self.assertIsNone(image["alt"])
            self.assertDatetimeFormat(image["created_at"])
            self.assertDatetimeFormat(image["updated_at"])

            # check the fie was saved
            file_path = os.path.abspath(
                str(settings.MEDIA_ROOT) + image["src"].split("media")[1]
            )
            self.assertTrue(os.path.exists(file_path))


# TODO test access permissions