"""VPCs and route tables"""
import pulumi
from pulumi_aws import cloudwatch, iam, ec2

config = pulumi.Config()
platform_k8s_config = config.require_object('platform_k8s')
services_k8s_cidr = config.require('services_k8s_cidr')
environment = config.get('environment')

platform_k8s_octet_prefix = '.'.join(platform_k8s_config['cidr'].split('.')[:2])

class AwsVpc(object):
    def __init__(self, **kwargs):
        self.environment = kwargs.get('environment')
        self.region = kwargs.get('region')
        self.root_tag_name = kwargs.get('root_tag_name')
        self.root_resource_name = kwargs.get('root_resource_name')
        self.vpc_cidr = kwargs.get('vpc_cidr')
        self.protect_resources = kwargs.get('protect_resources')
        self.vpc_cidr_octet_prefix = '.'.join(self.vpc_cidr.split('.')[:2])
        self.vpc = ec2.Vpc(
            f'{self.root_resource_name}-vpc-{self.environment}',
            cidr_block=self.vpc_cidr,
            instance_tenancy='default',
            enable_dns_hostnames=True,
            enable_dns_support=True,
            opts=pulumi.ResourceOptions(protect=self.protect_resources),
            tags={
                'Name': f'{self.root_tag_name} VPC {self.environment}'
            }
        )
        self.internet_gateway = ec2.InternetGateway(
            f'{self.root_resource_name}-vpc-ig-{self.environment}',
            vpc_id=self.vpc.id,
            opts=pulumi.ResourceOptions(protect=self.protect_resources),
            tags={
                'Name': f'{self.root_tag_name} VPC Internet Gateway {self.environment}'
            }
        )
        self.main_route_table = ec2.RouteTable(
            f'{self.root_resource_name}-route-table-{environment}',
            vpc_id=self.vpc.id,
            routes=[
                ec2.RouteTableRouteArgs(
                    cidr_block='0.0.0.0/0',
                    gateway_id=self.internet_gateway,
                )
            ],
            tags={
                'Name': f'{self.root_tag_name} route table {environment}'
            },
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )

    def create_subnet(self, az, third_octet, resource_name=None, create_route_table=False, public=True, color=None):
        if not resource_name:
            resource_name = '{root_resource_name}-{subnet_use}-subnet-{az}{color}-{environment}'.format(
                root_resource_name=self.root_resource_name,
                subnet_use='public' if public else 'private',
                az=az,
                color=''.join(['-', color]) if color else '',
                environment=self.environment,
            )
        subnet = ec2.Subnet(
            resource_name,
            vpc_id=self.vpc.id,
            availability_zone=f'{az}',
            map_public_ip_on_launch=public,
            cidr_block=f'{platform_k8s_octet_prefix}.{third_octet}.0/24',
            opts=pulumi.ResourceOptions(protect=self.protect_resources),
            tags={
                'Name': '{root_tag_name} {subnet_use} Subnet {az}{color} {environment}'.format(
                    root_tag_name=self.root_tag_name,
                    az=az,
                    environment=self.environment,
                    color=''.join([' ', color]) if color else '',
                    subnet_use='Public' if public else 'Private'
                )
            }
        )
        if not create_route_table:
            return subnet

        route_table = ec2.RouteTable(
            '{root_resource_name}-{subnet_use}-route-table-{az}{color}-{environment}'.format(
                root_resource_name=self.root_resource_name,
                az=az,
                color=''.join(['-', color]) if color else '',
                environment=self.environment,
                subnet_use='public' if public else 'private'
            ),
            vpc_id=self.vpc.id,
            routes=[
                ec2.RouteTableRouteArgs(
                    cidr_block='0.0.0.0/0',
                    gateway_id=self.internet_gateway,
                )
            ],
            opts=pulumi.ResourceOptions(protect=self.protect_resources),
            tags={
                'Name': '{root_tag_name} {subnet_use} route table {az}{color} {environment}'.format(
                    root_tag_name=self.root_tag_name,
                    az=az,
                    color=''.join([' ', color]) if color else '',
                    environment=self.environment,
                    subnet_use='Public' if public else 'Private'
                )
            },
        )
        subnet_assn = self.create_subnet_association(
            az, subnet.id,  route_table_id=route_table.id,
            resource_name='{root_resource_name}-utility-{purpose}-subnet-association-{az}{color}-{environment}'.format(
                    root_resource_name=self.root_resource_name,
                    purpose='public' if public else 'private',
                    az=az,
                    color=''.join(['-', color]) if color else '',
                    environment=self.environment,
                )
        )

        return subnet, route_table, subnet_assn

    def create_nat_gateway(self, az, subnet_id):
        nat_eip = ec2.Eip(
            f'{self.root_resource_name}-nat-eip-{az}-{self.environment}',
            vpc=True,
            tags={
                'Name': f'{self.root_tag_name} NAT EIP {az} {self.environment}'
            },
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )
        nat_gateway = ec2.NatGateway(
            f'{self.root_resource_name}-nat-gateway-{az}-{self.environment}',
            allocation_id=nat_eip.id,
            subnet_id=subnet_id.id,
            tags={
                'Name': f'{self.root_tag_name} NAT Gateway {az} {environment}'
            },
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )
        return {
            'eip': nat_eip,
            'nat_gateway': nat_gateway
        }

    def create_subnet_association(self, az, subnet_id, resource_name=None, purpose=None, route_table_id=None, color=None):
        if not resource_name:
            resource_name = f'{self.root_resource_name}-utility-{purpose}-subnet-association-{az}-{self.environment}'
        if not route_table_id:
            route_table_id = self.main_route_table.id
        return ec2.RouteTableAssociation(
            resource_name,
            subnet_id=subnet_id,
            route_table_id=route_table_id,
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )

    def create_vpc_endpoint(self):
        return ec2.VpcEndpoint(
            f'{self.root_resource_name}-vpc-endpoint-{self.environment}',
            # route_table_ids=something,
            service_name=f'com.amazonaws.{self.region}.s3',
            vpc_id=self.vpc.id,
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )

    def create_vpc_flow_logs(self):
        log_group = cloudwatch.LogGroup(
            f'{self.root_resource_name}-log-group-{self.environment}',
            name=f'/aws/flowlogs/{self.root_resource_name}',
            retention_in_days=60,
            tags={
                'Name': f'{self.root_tag_name} Flow Logs Group {environment}'
            },
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )
        flow_log_role = iam.Role(
            f'{self.root_resource_name}-log-role-{self.environment}',
            assume_role_policy="""{
                  "Version": "2012-10-17",
                  "Statement": [
                    {
                      "Sid": "",
                      "Effect": "Allow",
                      "Principal": {
                        "Service": "vpc-flow-logs.amazonaws.com"
                      },
                      "Action": "sts:AssumeRole"
                    }
                  ]
                }
                """,
            tags={
                'Name': f'{self.root_tag_name} Flow Logs Role {environment}'
            },
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )
        ec2.FlowLog(
            f'{self.root_resource_name}-flow-log-{self.environment}',
            iam_role_arn=flow_log_role.arn,
            log_destination=log_group.arn,
            traffic_type="ALL",
            vpc_id=self.vpc.id,
            tags={
                'Name': f'{self.root_tag_name} Flow Log {environment}'
            },
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )
        iam.RolePolicy(
            f'{self.root_resource_name}-log-role-policy-{self.environment}',
            role=flow_log_role.id,
            policy="""{
                        "Version": "2012-10-17",
                        "Statement": [
                          {
                            "Action": [
                              "logs:CreateLogGroup",
                              "logs:CreateLogStream",
                              "logs:PutLogEvents",
                              "logs:DescribeLogGroups",
                              "logs:DescribeLogStreams"
                            ],
                            "Effect": "Allow",
                            "Resource": "*"
                          }
                        ]
                      }
                      """,
            opts=pulumi.ResourceOptions(protect=self.protect_resources)
        )
