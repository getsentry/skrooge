from skrooge.utils import (
    determine_constrained_resource,
    determine_instance_count_required,
)

c2_standard_30_instance_data = {
    "regions": {
        "us": {},
        "us-central1": {
            "ondemand": 1.56606,
            "sud": 1.25285,
            "preemptible": 0.186,
            "cud-1y": 0.98655,
            "cud-3y": 0.62643,
        },
        "us-east1": {
            "ondemand": 1.56606,
            "sud": 1.25285,
            "preemptible": 0.186,
            "cud-1y": 0.98655,
            "cud-3y": 0.62643,
        },
        "us-east4": {
            "ondemand": 1.76358,
            "sud": 1.41086,
            "preemptible": 0.51156,
            "cud-1y": 1.05561,
            "cud-3y": 0.70554,
        },
        "us-east5": {
            "ondemand": 1.56606,
            "sud": 1.25285,
            "preemptible": 0.14112,
            "cud-1y": 0.98655,
            "cud-3y": 0.62643,
        },
        "us-west4": {
            "ondemand": 1.76358,
            "sud": 1.41086,
            "preemptible": 0.40542,
            "cud-1y": 1.05561,
            "cud-3y": 0.70554,
        },
        "us-west1": {
            "ondemand": 1.56606,
            "sud": 1.25285,
            "preemptible": 0.186,
            "cud-1y": 0.98655,
            "cud-3y": 0.62643,
        },
        "us-west2": {
            "ondemand": 1.88106,
            "sud": 1.50485,
            "preemptible": 0.5805,
            "cud-1y": 1.18497,
            "cud-3y": 0.75237,
        },
        "us-west3": {
            "ondemand": 1.88106,
            "sud": 1.50485,
            "preemptible": 0.48672,
            "cud-1y": 1.18497,
            "cud-3y": 0.75237,
        },
        "us-south1": {
            "ondemand": 1.84795,
            "sud": 1.47836,
            "preemptible": 0.18627,
            "cud-1y": 1.16413,
            "cud-3y": 0.73919,
        },
        "europe": {},
        "europe-central2": {
            "ondemand": 2.01759,
            "sud": 1.61407,
            "preemptible": 0.46374,
            "cud-1y": 1.26993,
            "cud-3y": 0.80706,
        },
        "europe-west1": {
            "ondemand": 1.72275,
            "sud": 1.3782,
            "preemptible": 0.41682,
            "cud-1y": 1.08522,
            "cud-3y": 0.68904,
        },
        "europe-west2": {
            "ondemand": 2.01759,
            "sud": 1.61407,
            "preemptible": 0.42936,
            "cud-1y": 1.26993,
            "cud-3y": 0.80706,
        },
        "europe-west3": {
            "ondemand": 2.01759,
            "sud": 1.61407,
            "preemptible": 0.6645,
            "cud-1y": 1.26993,
            "cud-3y": 0.80706,
        },
        "europe-west4": {
            "ondemand": 1.72404,
            "sud": 1.37923,
            "preemptible": 0.2349,
            "cud-1y": 1.08603,
            "cud-3y": 0.68967,
        },
        "europe-west6": {
            "ondemand": 2.19075,
            "sud": 1.7526,
            "preemptible": 0.55512,
            "cud-1y": 1.38003,
            "cud-3y": 0.87633,
        },
        "europe-west8": {
            "ondemand": 1.81663,
            "sud": 1.4533,
            "preemptible": 0.18312,
            "cud-1y": 1.1444,
            "cud-3y": 0.72666,
        },
        "europe-west9": {
            "ondemand": 1.81663,
            "sud": 1.4533,
            "preemptible": 0.18312,
            "cud-1y": 1.1444,
            "cud-3y": 0.72666,
        },
        "europe-west10": {
            "ondemand": 2.41173,
            "sud": 1.92939,
            "preemptible": 0.2189,
            "cud-1y": 1.51929,
            "cud-3y": 0.9647,
        },
        "europe-west12": {
            "ondemand": 2.02022,
            "sud": 1.61617,
            "preemptible": 0.18336,
            "cud-1y": 1.27265,
            "cud-3y": 0.80809,
        },
        "europe-north1": {
            "ondemand": 1.72416,
            "sud": 1.37933,
            "preemptible": 0.5622,
            "cud-1y": 1.08603,
            "cud-3y": 0.68973,
        },
        "europe-southwest1": {
            "ondemand": 1.84795,
            "sud": 1.47836,
            "preemptible": 0.18627,
            "cud-1y": 1.16413,
            "cud-3y": 0.73919,
        },
        "northamerica-northeast1": {
            "ondemand": 1.72404,
            "sud": 1.37923,
            "preemptible": 0.52836,
            "cud-1y": 1.08603,
            "cud-3y": 0.68967,
        },
        "northamerica-northeast2": {
            "ondemand": 1.72404,
            "sud": 1.37923,
            "preemptible": 0.41699,
            "cud-1y": 1.08603,
            "cud-3y": 0.68967,
        },
        "africa-south1": {
            "ondemand": 2.04841,
            "sud": 1.63873,
            "preemptible": 0.18592,
            "cud-1y": 1.29041,
            "cud-3y": 0.81937,
        },
        "asia": {},
        "asia-east": {},
        "asia-east1": {
            "ondemand": 1.81329,
            "sud": 1.45063,
            "preemptible": 0.41679,
            "cud-1y": 1.1424,
            "cud-3y": 0.72537,
        },
        "asia-east2": {
            "ondemand": 2.1912,
            "sud": 1.75296,
            "preemptible": 0.53652,
            "cud-1y": 1.38033,
            "cud-3y": 0.87645,
        },
        "asia-northeast": {},
        "me-west1": {
            "ondemand": 1.72267,
            "sud": 1.37813,
            "preemptible": 0.17365,
            "cud-1y": 1.0852,
            "cud-3y": 0.68907,
        },
        "me-central1": {
            "ondemand": 1.90276,
            "sud": 1.52221,
            "preemptible": 0.1727,
            "cud-1y": 1.19866,
            "cud-3y": 0.76111,
        },
        "me-central2": {
            "ondemand": 2.5057,
            "sud": 2.00456,
            "preemptible": 0.22742,
            "cud-1y": 1.57848,
            "cud-3y": 1.00229,
        },
        "asia-northeast1": {
            "ondemand": 2.00892,
            "sud": 1.60714,
            "preemptible": 0.27666,
            "cud-1y": 1.26564,
            "cud-3y": 0.80358,
        },
        "asia-northeast2": {
            "ondemand": 2.00892,
            "sud": 1.60714,
            "preemptible": 0.681,
            "cud-1y": 1.26735,
            "cud-3y": 0.80358,
        },
        "asia-northeast3": {
            "ondemand": 2.00892,
            "sud": 1.60714,
            "preemptible": 0.50202,
            "cud-1y": 1.26735,
            "cud-3y": 0.80358,
        },
        "asia-southeast": {},
        "asia-southeast1": {
            "ondemand": 1.93188,
            "sud": 1.5455,
            "preemptible": 0.61668,
            "cud-1y": 1.21698,
            "cud-3y": 0.77274,
        },
        "australia-southeast1": {
            "ondemand": 2.22204,
            "sud": 1.77763,
            "preemptible": 0.6306,
            "cud-1y": 1.40025,
            "cud-3y": 0.88884,
        },
        "australia-southeast2": {
            "ondemand": 2.22204,
            "sud": 1.77763,
            "preemptible": 0.53808,
            "cud-1y": 1.40025,
            "cud-3y": 0.88884,
        },
        "australia": {},
        "southamerica-east1": {
            "ondemand": 2.4858,
            "sud": 1.98864,
            "preemptible": 0.2382,
            "cud-1y": 1.5666,
            "cud-3y": 0.99435,
        },
        "asia-south1": {
            "ondemand": 1.88094,
            "sud": 1.50475,
            "preemptible": 0.55254,
            "cud-1y": 1.18476,
            "cud-3y": 0.75237,
        },
        "asia-southeast2": {
            "ondemand": 2.10575,
            "sud": 1.6846,
            "preemptible": 0.50958,
            "cud-1y": 1.32651,
            "cud-3y": 0.84229,
        },
        "asia-south2": {
            "ondemand": 1.88094,
            "sud": 1.50475,
            "preemptible": 0.58692,
            "cud-1y": 1.18476,
            "cud-3y": 0.75237,
        },
        "southamerica-west1": {
            "ondemand": 2.23947,
            "sud": 1.79157,
            "preemptible": 0.54187,
            "cud-1y": 1.41077,
            "cud-3y": 0.89579,
        },
    },
    "specs": {
        "cores": 30,
        "memory": 120,
        "local_ssd": 1,
        "gpu": 0,
        "sole_tenant": -1,
        "nested_virtualization": -1,
        "cpu": ["Cascade Lake"],
        "benchmark": 571147,
        "network_egress": 32,
        "regional_disk": 0,
    },
}


def test_determine_constrained_resource_cpu_bound():
    assert (
        determine_constrained_resource(c2_standard_30_instance_data, cpu=10000, mem=128)
        == "cores"
    )


def test_determine_constrained_resource_mem_bound():
    assert (
        determine_constrained_resource(c2_standard_30_instance_data, cpu=100, mem=12800)
        == "memory"
    )


def test_determine_instance_count_required_minimum_of_one_cpu():
    assert (
        determine_instance_count_required(c2_standard_30_instance_data, "cores", 10)
        == 1
    )


def test_determine_instance_count_required_minimum_of_one_memory():
    assert (
        determine_instance_count_required(c2_standard_30_instance_data, "memory", 10)
        == 1
    )


def test_determine_instance_count_required_cpu():
    assert (
        determine_instance_count_required(c2_standard_30_instance_data, "cores", 75000)
        == 3
    )


def test_determine_instance_count_required_memory():
    assert (
        determine_instance_count_required(
            c2_standard_30_instance_data, "memory", 389120
        )
        == 4
    )
