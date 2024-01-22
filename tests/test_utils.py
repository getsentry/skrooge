from skrooge.utils import determine_constrained_resource, determine_instance_count_required


def test_determine_constrained_resource_cpu_bound():
    instance_data = {
        "cpu": 30,
        "memory": 120,
        "local_ssd": 1,
        "network_egress": 32,
        "benchmark": 571147,
    }

    assert determine_constrained_resource(instance_data, cpu=10000, mem=128) == "cpu"

def test_determine_constrained_resource_mem_bound():
    instance_data = {
        "cpu": 30,
        "memory": 120,
        "local_ssd": 1,
        "network_egress": 32,
        "benchmark": 571147,
    }

    assert determine_constrained_resource(instance_data, cpu=100, mem=12800) == "memory"

def test_determine_instance_count_required_minimum_of_one_cpu():
    instance_data = {
        "cpu": 30,
        "memory": 120,
        "local_ssd": 1,
        "network_egress": 32,
        "benchmark": 571147,
    }

    assert determine_instance_count_required(instance_data, "cpu", 10) == 1

def test_determine_instance_count_required_minimum_of_one_memory():
    instance_data = {
        "cpu": 30,
        "memory": 120,
        "local_ssd": 1,
        "network_egress": 32,
        "benchmark": 571147,
    }

    assert determine_instance_count_required(instance_data, "memory", 10) == 1

def test_determine_instance_count_required_cpu():
    instance_data = {
        "cpu": 30,
        "memory": 120,
        "local_ssd": 1,
        "network_egress": 32,
        "benchmark": 571147,
    }

    assert determine_instance_count_required(instance_data, "cpu", 75000) == 3

def test_determine_instance_count_required_memory():
    instance_data = {
        "cpu": 30,
        "memory": 120,
        "local_ssd": 1,
        "network_egress": 32,
        "benchmark": 571147,
    }

    assert determine_instance_count_required(instance_data, "memory", 389120) == 4

