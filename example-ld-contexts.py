"""
Example LaunchDarkly contexts for testing the integration.
This file demonstrates different context types and attributes that can be used.
"""

from ldclient import Context

def create_user_context():
    """Create a basic user context"""
    return Context.builder('user-123') \
        .kind('user') \
        .name('John Doe') \
        .set('tier', 'premium') \
        .set('country', 'US') \
        .set('subscription_id', 'sub_123') \
        .build()

def create_organization_context():
    """Create an organization context"""
    return Context.builder('org-456') \
        .kind('organization') \
        .name('Acme Corp') \
        .set('plan', 'enterprise') \
        .set('region', 'us-west-2') \
        .set('employee_count', 500) \
        .build()

def create_device_context():
    """Create a device context"""
    return Context.builder('device-789') \
        .kind('device') \
        .set('os', 'iOS') \
        .set('version', '15.0') \
        .set('model', 'iPhone 13') \
        .set('app_version', '2.1.0') \
        .build()

def create_multi_context():
    """Create a multi-context with user and organization"""
    user_context = Context.builder('user-123') \
        .kind('user') \
        .name('Jane Smith') \
        .set('role', 'admin') \
        .build()
    
    org_context = Context.builder('org-456') \
        .kind('organization') \
        .name('Tech Corp') \
        .set('plan', 'pro') \
        .build()
    
    return Context.create_multi([user_context, org_context])

# Example usage in main.py:
# context = create_user_context()
# flag_value = ldclient.get().variation_detail(feature_flag_key, context, "Control")
