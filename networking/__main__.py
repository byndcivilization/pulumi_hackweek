"""VPC and networking architecture"""
import pulumi
# from vpc import AwsVpc
import components.platform_k8s as platform_k8s

from utils.autotag import register_auto_tags
# Automatically inject tags.
config = pulumi.Config()
register_auto_tags({
    'source': 'pulumi',
    'pulumi:Project': pulumi.get_project(),
    'pulumi:Stack': pulumi.get_stack(),
    'fedramp_boundary': config.require('fedramp_boundary'),
})


stack_catalog = dict()
stack_root, fields = platform_k8s.create_stack()
stack_catalog[stack_root] = fields






# import vpc
pulumi.export('stack_catalog', stack_catalog)