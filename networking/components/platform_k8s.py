import pulumi
from vpc import AwsVpc

PRIVATE_SUBNET_INCREMENTOR = 16

config = pulumi.Config()
environment = config.get('environment')
platform_k8s_config = config.require_object('platform_k8s')
utility_subnet_az = platform_k8s_config['availability_zones'][0]

def create_stack():
    platform_k8s_vpc = AwsVpc(
        environment=environment,
        # region=config.get('aws:region'),
        region='us-east-1',
        nat_enabled=platform_k8s_config['nat_enabled'],
        root_tag_name='Platform k8s',
        root_resource_name='platform-k8s',
        vpc_cidr=platform_k8s_config['cidr'],
        protect_resources=False
    )

    platform_azs = {i: {} for i in platform_k8s_config['availability_zones']}

    platform_k8s_public_utility_subnet = platform_k8s_vpc.create_subnet(
        utility_subnet_az, len(platform_k8s_config['availability_zones']),
        resource_name=f'{platform_k8s_vpc.root_resource_name}-utility-public-subnet-{environment}'
    )

    platform_k8s_public_utility_subnet_assoc = platform_k8s_vpc.create_subnet_association(
        utility_subnet_az, platform_k8s_public_utility_subnet.id,
        resource_name=f'{platform_k8s_vpc.root_resource_name}-utility-public-subnet-association-{environment}'
    )

    if platform_k8s_config.get('public_subnets'):
        for i, az in enumerate(platform_azs):
            platform_azs[az].setdefault('public_subnet', {})
            public_subnet, public_route_table, public_subnet_association = platform_k8s_vpc.create_subnet(
                az, i, create_route_table=True)
            platform_azs[az]['public_subnet']['subnet'] = public_subnet
            platform_azs[az]['public_subnet']['route_table'] = public_route_table
            platform_azs[az]['public_subnet']['subnet_association'] = public_subnet_association

    if platform_k8s_config['nat_enabled']:
        for az in platform_azs:
            platform_azs[az]['nat'] = platform_k8s_vpc.create_nat_gateway(az, platform_azs[az]['public_subnet']['subnet'])

    if platform_k8s_config.get('private_subnets'):
        i = PRIVATE_SUBNET_INCREMENTOR
        for color in platform_k8s_config.get('deploy_colors'):
            for az in platform_azs:
                platform_azs[az].setdefault('private_subnet', {}).setdefault(color, {})
                private_subnet, private_route_table, private_subnet_association = platform_k8s_vpc.create_subnet(
                    az, i, create_route_table=True, public=False, color=color)
                platform_azs[az]['private_subnet'][color]['subnet'] = private_subnet
                platform_azs[az]['private_subnet'][color]['route_table'] = private_route_table
                platform_azs[az]['private_subnet'][color]['subnet_association'] = private_subnet_association

                i += PRIVATE_SUBNET_INCREMENTOR

    if platform_k8s_config.get('vpc_endpoint'):
        platform_k8s_vpc_endpoint = platform_k8s_vpc.create_vpc_endpoint()

    if platform_k8s_config.get('vpc_flow_logs'):
        platform_k8s_vpc.create_vpc_flow_logs()




    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_vpc_id', platform_k8s_vpc.vpc.id)
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_protect_resources', platform_k8s_vpc.protect_resources)
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_public_utility_subnet_id', platform_k8s_public_utility_subnet.id)
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_public_utility_subnet_assoc_id', platform_k8s_public_utility_subnet_assoc.id)
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_public_vpc_endpoint_id', platform_k8s_vpc_endpoint.id)
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_internet_gateway_id', platform_k8s_vpc.internet_gateway.id)
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_main_route_table_id', platform_k8s_vpc.main_route_table.id)
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_nat_gateways',
                  {az: {
                      'eip_id': platform_azs[az]['nat']['eip'].id,
                      'eip': platform_azs[az]['nat']['eip'].public_ip,
                      'nat_gateway_id': platform_azs[az]['nat']['nat_gateway'].id
                  } for az in platform_azs}
                  )
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_public_subnets',
                  {az: {
                      'subnet_id': platform_azs[az]['public_subnet']['subnet'].id,
                      'route_table_id': platform_azs[az]['public_subnet']['route_table'].id,
                      'subnet_association_id': platform_azs[az]['public_subnet']['subnet_association'].id
                  } for az in platform_azs}
                  )
    pulumi.export(f'{platform_k8s_vpc.root_resource_name}_private_subnets',
                  {az: {
                      color: {'subnet_id': platform_azs[az]['private_subnet'][color]['subnet'].id,
                              'route_table_id': platform_azs[az]['private_subnet'][color]['route_table'].id,
                              'subnet_association_id': platform_azs[az]['private_subnet'][color][
                                  'subnet_association'].id} for color in platform_azs[az]['private_subnet'].keys()
                  } for az in platform_azs}

                  )

    return platform_k8s_vpc.root_resource_name,\
           [
               '_vpc_id', '_public_utility_subnet_id', '_public_utility_subnet_assoc_id', '_public_vpc_endpoint_id',
               '_internet_gateway_id', '_main_route_table_id', '_nat_gateways', '_public_subnets', '_private_subnets'
           ]
