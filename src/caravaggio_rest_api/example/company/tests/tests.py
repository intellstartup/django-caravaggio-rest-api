# -*- coding: utf-8 -*-
import os
import json
import logging
import time
import math

from datetime import datetime, timedelta
from dateutil import relativedelta

from caravaggio_rest_api.utils import delete_all_records
from caravaggio_rest_api.example.company.models import Company

from rest_framework import status
from django.urls import reverse

from caravaggio_rest_api.utils import default

from caravaggio_rest_api.tests import CaravaggioBaseTest

# Create your tests here.
from caravaggio_rest_api.example.company.api.serializers import CompanySerializerV1

CONTENTTYPE_JON = "application/json"

_logger = logging.getLogger()


class GetAllCompanyTest(CaravaggioBaseTest):
    """ Test module for Company model """

    companies = []

    persisted_companies = []

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()

        cls.crunchbase = cls.create_user(email="crunchbase@harvester.com", first_name="CrunchBase", last_name="Crawler")

        cls.manual_user_1 = cls.create_user(email="user@mycompany.com", first_name="Jorge", last_name="Clooney")

        delete_all_records(Company)

        current_path = os.path.dirname(os.path.abspath(__file__))
        cls.companies = GetAllCompanyTest.load_test_data("{}/companies.json".format(current_path), CompanySerializerV1)

    def step01_create_companies(self):
        for company in self.companies:
            _logger.info("POST Company: {}".format(company["name"]))
            response = self.api_client.post(
                reverse("company-list"), data=json.dumps(company, default=default), content_type=CONTENTTYPE_JON
            )
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
            self.persisted_companies.append(response.data["_id"])

        _logger.info("Persisted companies: {}".format(self.persisted_companies))

        # We need to wait until the data has been indexed (Cassandra-Solr)
        # We need to give time for the next search tests
        time.sleep(0.5)

    def step02_get_companies(self):
        for index, company_id in enumerate(self.persisted_companies):
            original_company = self.companies[index]
            path = "{0}{1}/".format(reverse("company-list"), company_id)
            _logger.info("Path: {}".format(path))
            response = self.api_client.get(path)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
            self.assertEqual(response.data["name"], original_company["name"])
            super(GetAllCompanyTest, self).assert_equal_dicts(
                response.data, original_company, ["_id", "created_at", "updated_at"]
            )

    def step03_search_text(self):
        """ We search any company that contains a text in the text field,
        that is a field that concentrates all the textual fields
        (corpus of the company)

        """
        path = "{0}?text=distributed".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        # BigML (position 2)
        self.assertEqual(response.data["results"][0]["name"], self.companies[1]["name"])
        super(GetAllCompanyTest, self).assert_equal_dicts(
            response.data["results"][0], self.companies[1], ["_id", "created_at", "updated_at", "score"]
        )

    def step04_search_specialties(self):
        """" Get companies that have "Internet" in their specialties.

        And get companies that have specialties that contains "*Internet*"
        in their name but do not have "Hardware"

        """
        path = "{0}?specialties=internet".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 2)

        # Get companies that contains *Internet* in their specialties
        # but do not contains "Hardware"
        path = "{0}?specialties=internet&specialties__not=hardware".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        # BigML (position 2)
        self.assertEqual(response.data["results"][0]["name"], self.companies[1]["name"])
        super(GetAllCompanyTest, self).assert_equal_dicts(
            response.data["results"][0], self.companies[1], ["_id", "created_at", "updated_at", "score"]
        )

    def step05_search_geo(self):
        """" Will get all the companies within 10 km from the point
             with longitude -123.25022 and latitude 44.59641.

        """
        path = "{0}?km=10&from=44.59641,-123.25022".format(reverse("company-geosearch-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["name"], self.companies[1]["name"])
        super(GetAllCompanyTest, self).assert_equal_dicts(
            response.data["results"][0], self.companies[1], ["_id", "created_at", "updated_at", "score"]
        )

    def step06_search_facets(self):
        """" Will get all the companies within 10 km from the point
             with longitude -123.25022 and latitude 44.59641.

        """
        start_date = datetime.now() - timedelta(days=50 * 365)
        end_date = datetime.now()
        r = relativedelta.relativedelta(end_date, start_date)
        expected_buckets = math.ceil((r.years * 12 + r.months) / 6)

        foundation_facet = f"start_date:{start_date:%Y-%m-%d},end_date:{end_date:%Y-%m-%d},gap_by:month,gap_amount:6"

        path = (
            f"{reverse('company-search-list')}facets/?facet.field.country_code=limit:1&"
            f"facet.field.specialties&facet.field.stock_symbol&facet.field.founders&"
            f"facet.field.foundation_date={foundation_facet}"
        )
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data["fields"]["country_code"]), 1)
        self.assertEqual(response.data["fields"]["country_code"][0]["text"], "USA")
        self.assertEqual(response.data["fields"]["country_code"][0]["count"], 2)

        self.assertEqual(len(response.data["fields"]["stock_symbol"]), 2)
        self.assertEqual(response.data["fields"]["stock_symbol"][0]["text"], "XXX")
        self.assertEqual(response.data["fields"]["stock_symbol"][0]["count"], 1)
        self.assertEqual(response.data["fields"]["stock_symbol"][1]["text"], "YYY")
        self.assertEqual(response.data["fields"]["stock_symbol"][1]["count"], 1)

        self.assertEqual(len(response.data["fields"]["founders"]), 6)

        self.assertEqual(len(response.data["fields"]["specialties"]), 5)
        self.assertEqual(response.data["fields"]["specialties"][0]["text"], "Internet")
        self.assertEqual(response.data["fields"]["specialties"][0]["count"], 2)
        self.assertEqual(response.data["fields"]["specialties"][1]["text"], "Hardware")
        self.assertEqual(response.data["fields"]["specialties"][1]["count"], 1)
        self.assertEqual(response.data["fields"]["specialties"][2]["text"], "Machine Learning")
        self.assertEqual(response.data["fields"]["specialties"][2]["count"], 1)
        self.assertEqual(response.data["fields"]["specialties"][3]["text"], "Predictive Analytics")
        self.assertEqual(response.data["fields"]["specialties"][3]["count"], 1)
        self.assertEqual(response.data["fields"]["specialties"][4]["text"], "Telecommunications")
        self.assertEqual(response.data["fields"]["specialties"][4]["count"], 1)

        self.assertIn(len(response.data["dates"]["foundation_date"]), [expected_buckets, expected_buckets + 1])

        def get_date_bucket_text(start_date, bucket_num, months_bw_buckets):
            return (
                (start_date + relativedelta.relativedelta(months=+bucket_num * months_bw_buckets))
                .replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                .strftime("%Y-%m-%dT%H:%M:%SZ")
            )

        self.assertEqual(response.data["dates"]["foundation_date"][52]["text"], get_date_bucket_text(start_date, 52, 6))
        self.assertEqual(response.data["dates"]["foundation_date"][84]["text"], get_date_bucket_text(start_date, 84, 6))

    def step07_search_facets_ranges(self):
        """" Let's change the foundation_date facet range by all the years from
        1st Jan 2010 til today. Total: 8 years/buckets

        """
        path = (
            f"{reverse('company-search-list')}facets/?facet.field.foundation_date=start_date:2010-05-20,"
            f"end_date:2015-06-10,gap_by:year,gap_amount:1"
        )

        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["dates"]["foundation_date"]), 6)

        buckets = {bucket["text"]: bucket["count"] for bucket in response.data["dates"]["foundation_date"]}

        self.assertTrue("2011-01-01T00:00:00Z" in buckets)
        self.assertEqual(buckets["2011-01-01T00:00:00Z"], 1)

    def step08_search_facets_narrow(self):
        """" Drill down when selection facets

        """
        path = (
            "{0}facets/?facet.field.specialties&facet.field.country_code&"
            "selected_facets=specialties_exact:hardware&"
            "selected_facets=country_code_exact:usa".format(reverse("company-search-list"))
        )
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(len(response.data["fields"]["country_code"]), 1)
        self.assertEqual(response.data["fields"]["country_code"][0]["text"], "USA")
        self.assertEqual(response.data["fields"]["country_code"][0]["count"], 1)

        self.assertEqual(len(response.data["fields"]["specialties"]), 5)

        specialties = {specialty["text"]: specialty["count"] for specialty in response.data["fields"]["specialties"]}

        self.assertTrue("Hardware" in specialties)
        self.assertEqual(specialties["Hardware"], 1)

        self.assertTrue("Internet" in specialties)
        self.assertEqual(specialties["Internet"], 1)

        self.assertTrue("Machine Learning" in specialties)
        self.assertEqual(specialties["Machine Learning"], 0)

        self.assertTrue("Predictive Analytics" in specialties)
        self.assertEqual(specialties["Predictive Analytics"], 0)

        self.assertTrue("Telecommunications" in specialties)
        self.assertEqual(specialties["Telecommunications"], 1)

    def step09_fuzzy_search(self):
        # Find companies that contains the words "on-premises services" with 2 words within
        # each other.
        # The BigML Description: "BigML offers cloud-based and on-premises machine learning services, distributed ...",
        path = "{0}?short_description__fuzzy=on-premises services~2".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["name"], "BigML")

        # Now we search using the same criteria than before but adding another criteria, in this case
        # the matching of a word as part of the description with 1 letter of difference.
        path = "{0}?short_description__fuzzy=on-premises services~2,provide~1".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["total"], 2)

    def step10_within_search(self):
        # Find companies that the point is inside a radius of 10 units from the 40.0, -120.0 point
        path = "{0}?point=IsWithin(BUFFER(POINT(40.0 -120.0),10.0))".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["name"], "BigML")

        # Find companies that the point is inside a radius of 10 units from the 40.0, -120.0 point
        path = "{0}?point=IsWithin(BUFFER(POINT(95.0 95.0),10.0))".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Stealth Communications")

    def step11_intersects_search(self):
        # Find companies that the line string contains the point 50, 20
        path = "{0}?linestring=Intersects(POINT(50 20))".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["name"], "BigML")

        # Find companies that the line string contains the point 30, 10
        path = "{0}?linestring=Intersects(POINT(30 10))".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["total"], 1)
        self.assertEqual(response.data["results"][0]["name"], "Stealth Communications")

    def step12_heatmap_facet(self):
        # Find the heatmap for the company with name = BigML
        path = "{0}facets/?name=BigML&facet.heatmap.point=gridLevel:6".format(reverse("company-search-list"))
        _logger.info("Path: {}".format(path))
        response = self.api_client.get(path)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertEqual(response.data["objects"]["count"], 1)
        self.assertEqual(response.data["objects"]["results"][0]["name"], "BigML")
        self.assertEqual(len(response.data["heatmaps"]), 1)
        self.assertEqual(response.data["heatmaps"]["point"]["gridLevel"], 6)
