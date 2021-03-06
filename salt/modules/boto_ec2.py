# -*- coding: utf-8 -*-
'''
Connection module for Amazon EC2

.. versionadded:: 2015.8.0

:configuration: This module accepts explicit EC2 credentials but can also
    utilize IAM roles assigned to the instance trough Instance Profiles.
    Dynamic credentials are then automatically obtained from AWS API and no
    further configuration is necessary. More Information available at:

    .. code-block:: text

        http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/iam-roles-for-amazon-ec2.html

    If IAM roles are not used you need to specify them either in a pillar or
    in the minion's config file:

    .. code-block:: yaml

        ec2.keyid: GKTADJGHEIQSXMKKRBJ08H
        ec2.key: askdjghsdfjkghWupUjasdflkdfklgjsdfjajkghs

    A region may also be specified in the configuration:

    .. code-block:: yaml

        ec2.region: us-east-1

    If a region is not specified, the default is us-east-1.

    It's also possible to specify key, keyid and region via a profile, either
    as a passed in dict, or as a string to pull from pillars or minion config:

    .. code-block:: yaml

        myprofile:
            keyid: GKTADJGHEIQSXMKKRBJ08H
            key: askdjghsdfjkghWupUjasdflkdfklgjsdfjajkghs
            region: us-east-1

:depends: boto

'''
# keep lint from choking on _get_conn and _cache_id
#pylint: disable=E0602

# Import Python libs
from __future__ import absolute_import
import logging
import time
from distutils.version import LooseVersion as _LooseVersion  # pylint: disable=import-error,no-name-in-module

# Import Salt libs
import salt.utils.compat
import salt.ext.six as six
from salt.exceptions import SaltInvocationError, CommandExecutionError

# Import third party libs
try:
    # pylint: disable=unused-import
    import boto
    import boto.ec2
    # pylint: enable=unused-import
    HAS_BOTO = True
except ImportError:
    HAS_BOTO = False


log = logging.getLogger(__name__)


def __virtual__():
    '''
    Only load if boto libraries exist and if boto libraries are greater than
    a given version.
    '''
    required_boto_version = '2.8.0'
    # the boto_ec2 execution module relies on the connect_to_region() method
    # which was added in boto 2.8.0
    # https://github.com/boto/boto/commit/33ac26b416fbb48a60602542b4ce15dcc7029f12
    if not HAS_BOTO:
        return False
    elif _LooseVersion(boto.__version__) < _LooseVersion(required_boto_version):
        return False
    return True


def __init__(opts):
    salt.utils.compat.pack_dunder(__name__)
    if HAS_BOTO:
        __utils__['boto.assign_funcs'](__name__, 'ec2')


def get_zones(region=None, key=None, keyid=None, profile=None):
    '''
    Get a list of AZs for the configured region.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.get_zones
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    return [z.name for z in conn.get_all_zones()]


def find_instances(instance_id=None, name=None, tags=None, region=None,
                   key=None, keyid=None, profile=None, return_objs=False):

    '''
    Given instance properties, find and return matching instance ids

    CLI Examples:

    .. code-block:: bash

        salt myminion boto_ec2.find_instances # Lists all instances
        salt myminion boto_ec2.find_instances name=myinstance
        salt myminion boto_ec2.find_instances tags='{"mytag": "value"}'

    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    try:
        filter_parameters = {'filters': {}}

        if instance_id:
            filter_parameters['instance_ids'] = [instance_id]

        if name:
            filter_parameters['filters']['tag:Name'] = name

        if tags:
            for tag_name, tag_value in six.iteritems(tags):
                filter_parameters['filters']['tag:{0}'.format(tag_name)] = tag_value

        reservations = conn.get_all_instances(**filter_parameters)
        instances = [i for r in reservations for i in r.instances]
        log.debug('The filters criteria {0} matched the following '
                  'instances:{1}'.format(filter_parameters, instances))

        if instances:
            if return_objs:
                return instances
            return [instance.id for instance in instances]
        else:
            return False
    except boto.exception.BotoServerError as exc:
        log.error(exc)
        return False


def create_image(ami_name, instance_id=None, instance_name=None, tags=None, region=None,
                 key=None, keyid=None, profile=None, description=None, no_reboot=False,
                 dry_run=False):
    '''
    Given instance properties that define exactly one instance, create AMI and return AMI-id.

    CLI Examples:

    .. code-block:: bash

        salt myminion boto_ec2.create_instance ami_name instance_name=myinstance
        salt myminion boto_ec2.create_instance another_ami_name tags='{"mytag": "value"}' description='this is my ami'

    '''

    instances = find_instances(instance_id=instance_id, name=instance_name, tags=tags,
                               region=region, key=key, keyid=keyid, profile=profile,
                               return_objs=True)

    if not instances:
        log.error('Source instance not found')
        return False
    if len(instances) > 1:
        log.error('Multiple instances found, must match exactly only one instance to create an image from')
        return False

    instance = instances[0]
    try:
        return instance.create_image(ami_name, description=description,
                                     no_reboot=no_reboot, dry_run=dry_run)
    except boto.exception.BotoServerError as exc:
        log.error(exc)
        return False


def find_images(ami_name=None, executable_by=None, owners=None, image_ids=None, tags=None,
                region=None, key=None, keyid=None, profile=None, return_objs=False):

    '''
    Given image properties, find and return matching AMI ids

    CLI Examples:

    .. code-block:: bash

        salt myminion boto_ec2.find_instances tags='{"mytag": "value"}'

    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    try:
        filter_parameters = {'filters': {}}

        if image_ids:
            filter_parameters['image_ids'] = [image_ids]

        if executable_by:
            filter_parameters['executable_by'] = [executable_by]

        if owners:
            filter_parameters['owners'] = [owners]

        if ami_name:
            filter_parameters['filters']['name'] = ami_name

        if tags:
            for tag_name, tag_value in six.iteritems(tags):
                filter_parameters['filters']['tag:{0}'.format(tag_name)] = tag_value

        images = conn.get_all_images(**filter_parameters)
        log.debug('The filters criteria {0} matched the following '
                  'images:{1}'.format(filter_parameters, images))

        if images:
            if return_objs:
                return images
            return [image.id for image in images]
        else:
            return False
    except boto.exception.BotoServerError as exc:
        log.error(exc)
        return False


def terminate(instance_id=None, name=None, region=None,
              key=None, keyid=None, profile=None):
    '''
    Terminate the instance described by instance_id or name.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.terminate name=myinstance
        salt myminion boto_ec2.terminate instance_id=i-a46b9f
    '''
    instances = find_instances(instance_id=instance_id, name=name,
                               region=region, key=key, keyid=keyid,
                               profile=profile, return_objs=True)
    if instances in (False, None):
        return instances

    if len(instances) == 1:
        instances[0].terminate()
        return True
    else:
        log.warning('refusing to terminate multiple instances at once')
        return False


def get_id(name=None, tags=None, region=None, key=None,
           keyid=None, profile=None):

    '''
    Given instace properties, return the instance id if it exist.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.get_id myinstance

    '''
    instance_ids = find_instances(name=name, tags=tags, region=region, key=key,
                                  keyid=keyid, profile=profile)
    if instance_ids:
        log.info("Instance ids: {0}".format(" ".join(instance_ids)))
        if len(instance_ids) == 1:
            return instance_ids[0]
        else:
            raise CommandExecutionError('Found more than one instance '
                                        'matching the criteria.')
    else:
        log.warning('Could not find instance.')
        return None


def exists(instance_id=None, name=None, tags=None, region=None, key=None,
           keyid=None, profile=None):
    '''
    Given a instance id, check to see if the given instance id exists.

    Returns True if the given an instance with the given id, name, or tags
    exists; otherwise, False is returned.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.exists myinstance
    '''
    instances = find_instances(instance_id=instance_id, name=name, tags=tags)
    if instances:
        log.info('instance exists.')
        return True
    else:
        log.warning('instance does not exist.')
        return False


def run(image_id, name=None, tags=None, instance_type='m1.small',
        key_name=None, security_groups=None, user_data=None, placement=None,
        region=None, key=None, keyid=None, profile=None):
    '''
    Create and start an EC2 instance.

    Returns True if the instance was created; otherwise False.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.run ami-b80c2b87 name=myinstance

    '''
    #TODO: support multi-instance reservations

    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    reservation = conn.run_instances(image_id, instance_type=instance_type,
                                     key_name=key_name,
                                     security_groups=security_groups,
                                     user_data=user_data,
                                     placement=placement)
    if not reservation:
        log.warning('instances could not be reserved')
        return False

    instance = reservation.instances[0]

    status = 'pending'
    while status == 'pending':
        time.sleep(5)
        status = instance.update()
    if status == 'running':
        if name:
            instance.add_tag('Name', name)
        if tags:
            instance.add_tags(tags)
        return True
    else:
        log.warning('instance could not be started -- '
                    'status is "{0}"'.format(status))


def get_key(key_name, region=None, key=None, keyid=None, profile=None):
    '''
    Check to see if a key exists. Returns fingerprint and name if
    it does and False if it doesn't
    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.get_key mykey
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    try:
        key = conn.get_key_pair(key_name)
        log.debug("the key to return is : {0}".format(key))
        if key is None:
            return False
        return key.name, key.fingerprint
    except boto.exception.BotoServerError as e:
        log.debug(e)
        return False


def create_key(key_name, save_path, region=None, key=None, keyid=None,
               profile=None):
    '''
    Creates a key and saves it to a given path.
    Returns the private key.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.create mykey /root/
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    try:
        key = conn.create_key_pair(key_name)
        log.debug("the key to return is : {0}".format(key))
        key.save(save_path)
        return key.material
    except boto.exception.BotoServerError as e:
        log.debug(e)
        return False


def import_key(key_name, public_key_material, region=None, key=None,
               keyid=None, profile=None):
    '''
    Imports the public key from an RSA key pair that you created with a third-party tool.
    Supported formats:
    - OpenSSH public key format (e.g., the format in ~/.ssh/authorized_keys)
    - Base64 encoded DER format
    - SSH public key file format as specified in RFC4716
    - DSA keys are not supported. Make sure your key generator is set up to create RSA keys.
    Supported lengths: 1024, 2048, and 4096.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.import mykey publickey
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    try:
        key = conn.import_key_pair(key_name, public_key_material)
        log.debug("the key to return is : {0}".format(key))
        return key.fingerprint
    except boto.exception.BotoServerError as e:
        log.debug(e)
        return False


def delete_key(key_name, region=None, key=None, keyid=None, profile=None):
    '''
    Deletes a key. Always returns True

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.delete_key mykey
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    try:
        key = conn.delete_key_pair(key_name)
        log.debug("the key to return is : {0}".format(key))
        return key
    except boto.exception.BotoServerError as e:
        log.debug(e)
        return False


def get_keys(keynames=None, filters=None, region=None, key=None,
             keyid=None, profile=None):
    '''
    Gets all keys or filters them by name and returns a list.
    keynames (list):: A list of the names of keypairs to retrieve.
    If not provided, all key pairs will be returned.
    filters (dict) :: Optional filters that can be used to limit the
    results returned. Filters are provided in the form of a dictionary
    consisting of filter names as the key and filter values as the
    value. The set of allowable filter names/values is dependent on
    the request being performed. Check the EC2 API guide for details.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.get_keys
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    try:
        keys = conn.get_all_key_pairs(keynames, filters)
        log.debug("the key to return is : {0}".format(keys))
        key_values = []
        if keys:
            for key in keys:
                key_values.append(key.name)
        return key_values
    except boto.exception.BotoServerError as e:
        log.debug(e)
        return False


def get_attribute(attribute, instance_name=None, instance_id=None, region=None, key=None, keyid=None, profile=None):
    '''
    Get an EC2 instance attribute.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.get_attribute name=my_instance attribute=sourceDestCheck

    Available attributes:
        * instanceType
        * kernel
        * ramdisk
        * userData
        * disableApiTermination
        * instanceInitiatedShutdownBehavior
        * rootDeviceName
        * blockDeviceMapping
        * productCodes
        * sourceDestCheck
        * groupSet
        * ebsOptimized
        * sriovNetSupport
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    attribute_list = ['instanceType', 'kernel', 'ramdisk', 'userData', 'disableApiTermination',
                      'instanceInitiatedShutdownBehavior', 'rootDeviceName', 'blockDeviceMapping', 'productCodes',
                      'sourceDestCheck', 'groupSet', 'ebsOptimized', 'sriovNetSupport']
    if not any((instance_name, instance_id)):
        raise SaltInvocationError('At least one of the following must be specified: instance_name or instance_id.')
    if instance_name and instance_id:
        raise SaltInvocationError('Both instance_name and instance_id can not be specified in the same command.')
    if attribute not in attribute_list:
        raise SaltInvocationError('Attribute must be one of: {0}.'.format(attribute_list))
    try:
        if instance_name:
            instances = find_instances(name=instance_name, region=region, key=key, keyid=keyid, profile=profile)
            if len(instances) != 1:
                raise CommandExecutionError('Found more than one EC2 instance matching the criteria.')
            instance_id = instances[0]
        instance_attribute = conn.get_instance_attribute(instance_id, attribute)
        if not instance_attribute:
            return False
        return {attribute: instance_attribute[attribute]}
    except boto.exception.BotoServerError as exc:
        log.error(exc)
        return False


def set_attribute(attribute, attribute_value, instance_name=None, instance_id=None, region=None, key=None, keyid=None,
                  profile=None):
    '''
    Set an EC2 instance attribute.
    Returns whether the operation succeeded or not.

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.set_attribute instance_name=my_instance \
                attribute=sourceDestCheck attribute_value=False

    Available attributes:
        * instanceType
        * kernel
        * ramdisk
        * userData
        * disableApiTermination
        * instanceInitiatedShutdownBehavior
        * rootDeviceName
        * blockDeviceMapping
        * productCodes
        * sourceDestCheck
        * groupSet
        * ebsOptimized
        * sriovNetSupport
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)

    attribute_list = ['instanceType', 'kernel', 'ramdisk', 'userData', 'disableApiTermination',
                      'instanceInitiatedShutdownBehavior', 'rootDeviceName', 'blockDeviceMapping', 'productCodes',
                      'sourceDestCheck', 'groupSet', 'ebsOptimized', 'sriovNetSupport']
    if not any((instance_name, instance_id)):
        raise SaltInvocationError('At least one of the following must be specified: instance_name or instance_id.')
    if instance_name and instance_id:
        raise SaltInvocationError('Both instance_name and instance_id can not be specified in the same command.')
    if attribute not in attribute_list:
        raise SaltInvocationError('Attribute must be one of: {0}.'.format(attribute_list))
    try:
        if instance_name:
            instances = find_instances(name=instance_name, region=region, key=key, keyid=keyid, profile=profile)
            if len(instances) != 1:
                raise CommandExecutionError('Found more than one EC2 instance matching the criteria.')
            instance_id = instances[0]
        attribute = conn.modify_instance_attribute(instance_id, attribute, attribute_value)
        if not attribute:
            return False
        return attribute
    except boto.exception.BotoServerError as exc:
        log.error(exc)
        return False


def get_network_interface_id(name, region=None, key=None, keyid=None,
                             profile=None):
    '''
    Get an Elastic Network Interface id from its name tag.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.get_network_interface_id name=my_eni
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)
    r = {}
    try:
        enis = conn.get_all_network_interfaces(filters={'tag:Name': name})
    except boto.exception.EC2ResponseError as e:
        r['error'] = __utils__['boto.get_error'](e)
    if not enis:
        r['error'] = {'message': 'No ENIs found.'}
    elif len(enis) > 1:
        r['error'] = {'message': 'Name specified is tagged on multiple ENIs.'}
    if 'error' in r:
        return r
    eni = enis[0]
    r['result'] = eni.id
    return r


def get_network_interface(name=None, network_interface_id=None, region=None,
                          key=None, keyid=None, profile=None):
    '''
    Get an Elastic Network Interface.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.get_network_interface name=my_eni
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)
    r = {}
    result = _get_network_interface(conn, name, network_interface_id)
    if 'error' in result:
        if result['error']['message'] == 'No ENIs found.':
            r['result'] = None
            return r
        return result
    eni = result['result']
    r['result'] = _describe_network_interface(eni)
    return r


def _get_network_interface(conn, name=None, network_interface_id=None):
    r = {}
    if not (name or network_interface_id):
        raise SaltInvocationError(
            'Either name or network_interface_id must be provided.'
        )
    try:
        if network_interface_id:
            enis = conn.get_all_network_interfaces([network_interface_id])
        else:
            enis = conn.get_all_network_interfaces(filters={'tag:Name': name})
    except boto.exception.EC2ResponseError as e:
        r['error'] = __utils__['boto.get_error'](e)
    if not enis:
        r['error'] = {'message': 'No ENIs found.'}
    elif len(enis) > 1:
        r['error'] = {'message': 'Name specified is tagged on multiple ENIs.'}
    if 'error' in r:
        return r
    eni = enis[0]
    r['result'] = eni
    return r


def _describe_network_interface(eni):
    r = {}
    for attr in ['status', 'description', 'availability_zone', 'requesterId',
                 'requester_managed', 'mac_address', 'private_ip_address',
                 'vpc_id', 'id', 'source_dest_check', 'owner_id', 'tags',
                 'subnet_id', 'associationId', 'publicDnsName', 'owner_id',
                 'ipOwnerId', 'publicIp', 'allocationId']:
        if hasattr(eni, attr):
            r[attr] = getattr(eni, attr)
    r['region'] = eni.region.name
    r['groups'] = []
    for group in eni.groups:
        r['groups'].append({'name': group.name, 'id': group.id})
    r['private_ip_addresses'] = []
    for address in eni.private_ip_addresses:
        r['private_ip_addresses'].append(
            {'private_ip_address': address.private_ip_address,
             'primary': address.primary}
        )
    r['attachment'] = {}
    for attr in ['status', 'attach_time', 'device_index',
                 'delete_on_termination', 'instance_id',
                 'instance_owner_id', 'id']:
        if hasattr(eni.attachment, attr):
            r['attachment'][attr] = getattr(eni.attachment, attr)
    return r


def create_network_interface(
        name, subnet_id, private_ip_address=None, description=None,
        groups=None, region=None, key=None, keyid=None, profile=None):
    '''
    Create an Elastic Network Interface.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.create_network_interface my_eni subnet-12345 description=my_eni groups=['my_group']
    '''
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)
    r = {}
    result = _get_network_interface(conn, name)
    if 'result' in result:
        r['error'] = {'message': 'An ENI with this Name tag already exists.'}
        return r
    vpc_id = __salt__['boto_vpc.get_subnet_association'](
        [subnet_id], region=region, key=key, keyid=keyid, profile=profile
    )
    vpc_id = vpc_id.get('vpc_id')
    if not vpc_id:
        msg = 'subnet_id {0} does not map to a valid vpc id.'.format(subnet_id)
        r['error'] = {'message': msg}
        return r
    _groups = __salt__['boto_secgroup.convert_to_group_ids'](
        groups, vpc_id=vpc_id, region=region, key=key,
        keyid=keyid, profile=profile
    )
    try:
        eni = conn.create_network_interface(
            subnet_id,
            private_ip_address=private_ip_address,
            description=description,
            groups=_groups
        )
        eni.add_tag('Name', name)
    except boto.exception.EC2ResponseError as e:
        r['error'] = __utils__['boto.get_error'](e)
        return r
    r['result'] = _describe_network_interface(eni)
    return r


def delete_network_interface(
        name=None, network_interface_id=None, region=None, key=None,
        keyid=None, profile=None):
    '''
    Create an Elastic Network Interface.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.create_network_interface my_eni subnet-12345 description=my_eni groups=['my_group']
    '''
    if not (name or network_interface_id):
        raise SaltInvocationError(
            'Either name or network_interface_id must be provided.'
        )
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)
    r = {}
    result = _get_network_interface(conn, name, network_interface_id)
    if 'error' in result:
        return result
    eni = result['result']
    try:
        info = _describe_network_interface(eni)
        network_interface_id = info['id']
    except KeyError:
        r['error'] = {'message': 'ID not found for this network interface.'}
        return r
    try:
        r['result'] = conn.delete_network_interface(network_interface_id)
    except boto.exception.EC2ResponseError as e:
        r['error'] = __utils__['boto.get_error'](e)
    return r


def attach_network_interface(
        name=None, network_interface_id=None, instance_id=None,
        device_index=None, region=None, key=None, keyid=None, profile=None):
    '''
    Attach an Elastic Network Interface.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.create_network_interface my_eni subnet-12345 description=my_eni groups=['my_group']
    '''
    if not (name or network_interface_id):
        raise SaltInvocationError(
            'Either name or network_interface_id must be provided.'
        )
    if not (instance_id and device_index):
        raise SaltInvocationError(
            'instance_id and device_index are required parameters.'
        )
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)
    r = {}
    result = _get_network_interface(conn, name, network_interface_id)
    if 'error' in result:
        return result
    eni = result['result']
    try:
        info = _describe_network_interface(eni)
        network_interface_id = info['id']
    except KeyError:
        r['error'] = {'message': 'ID not found for this network interface.'}
        return r
    try:
        r['result'] = conn.attach_network_interface(
            network_interface_id, instance_id, device_index
        )
    except boto.exception.EC2ResponseError as e:
        r['error'] = __utils__['boto.get_error'](e)
    return r


def detach_network_interface(
        name=None, network_interface_id=None, attachment_id=None,
        force=False, region=None, key=None, keyid=None, profile=None):
    '''
    Detach an Elastic Network Interface.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.detach_network_interface my_eni
    '''
    if not (name or network_interface_id or attachment_id):
        raise SaltInvocationError(
            'Either name or network_interface_id or attachment_id must be'
            ' provided.'
        )
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)
    r = {}
    if not attachment_id:
        result = _get_network_interface(conn, name, network_interface_id)
        if 'error' in result:
            return result
        eni = result['result']
        info = _describe_network_interface(eni)
        try:
            attachment_id = info['attachment']['id']
        except KeyError:
            r['error'] = {'message': 'Attachment id not found for this ENI.'}
            return r
    try:
        r['result'] = conn.detach_network_interface(attachment_id, force)
    except boto.exception.EC2ResponseError as e:
        r['error'] = __utils__['boto.get_error'](e)
    return r


def modify_network_interface_attribute(
        name=None, network_interface_id=None, attr=None,
        value=None, region=None, key=None, keyid=None, profile=None):
    '''
    Modify an attribute of an Elastic Network Interface.

    .. versionadded:: Boron

    CLI Example:

    .. code-block:: bash

        salt myminion boto_ec2.modify_network_interface_attribute my_eni attr=description value='example description'
    '''
    if not (name or network_interface_id):
        raise SaltInvocationError(
            'Either name or network_interface_id must be provided.'
        )
    if attr is None and value is None:
        raise SaltInvocationError(
            'attr and value must be provided.'
        )
    r = {}
    conn = _get_conn(region=region, key=key, keyid=keyid, profile=profile)
    result = _get_network_interface(conn, name, network_interface_id)
    if 'error' in result:
        return result
    eni = result['result']
    info = _describe_network_interface(eni)
    network_interface_id = info['id']
    # munge attr into what the API requires
    if attr == 'groups':
        _attr = 'groupSet'
    elif attr == 'source_dest_check':
        _attr = 'sourceDestCheck'
    elif attr == 'delete_on_termination':
        _attr = 'deleteOnTermination'
    else:
        _attr = attr
    _value = value
    if info.get('vpc_id') and _attr == 'groupSet':
        _value = __salt__['boto_secgroup.convert_to_group_ids'](
            value, vpc_id=info.get('vpc_id'), region=region, key=key,
            keyid=keyid, profile=profile
        )
        if not _value:
            r['error'] = {
                'message': ('Security groups do not map to valid security'
                            ' group ids')
            }
            return r
    _attachment_id = None
    if _attr == 'deleteOnTermination':
        try:
            _attachment_id = info['attachment']['id']
        except KeyError:
            r['error'] = {
                'message': ('No attachment id found for this ENI. The ENI must'
                            ' be attached before delete_on_termination can be'
                            ' modified')
            }
            return r
    try:
        r['result'] = conn.modify_network_interface_attribute(
            network_interface_id, _attr, _value, attachment_id=_attachment_id
        )
    except boto.exception.EC2ResponseError as e:
        r['error'] = __utils__['boto.get_error'](e)
    return r
