import json
import os
import socket
import urllib2

from django import forms
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse, HttpResponseNotFound, \
    HttpResponseRedirect, HttpResponseForbidden
from django.shortcuts import get_object_or_404, render_to_response
from django.template import RequestContext

from object_permissions import get_model_perms, get_user_perms, grant, revoke, \
    get_users, get_groups, get_group_perms
from object_permissions.views.permissions import ObjectPermissionFormNewUsers
from ganeti.models import *
from util.portforwarder import forward_port

# Regex for a resolvable hostname
FQDN_RE = r'^[\w]+(\.[\w]+)*$'


@login_required
def detail(request, cluster_slug):
    """
    Display details of a cluster
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    user = request.user
    if not (user.is_superuser or user.has_perm('admin', cluster)):
        return HttpResponseForbidden("You do not have sufficient privileges")
    
    vmlist = VirtualMachine.objects.filter(cluster__exact=cluster)
    return render_to_response("cluster/detail.html", {
        'cluster': cluster,
        'user': request.user,
        'vmlist' : vmlist
        },
        context_instance=RequestContext(request),
    )


@login_required
def cluster_users(request, cluster_slug):
    """
    Display all of the users of a cluster
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    user = request.user
    if not (user.is_superuser or user.has_perm('admin', cluster)):
        return HttpResponseForbidden("You do not have sufficient privileges")
    
    users = get_users(cluster)
    groups = get_groups(cluster)
    return render_to_response("cluster/users.html", \
                        {'cluster': cluster, 'users':users, 'groups':groups}, \
        context_instance=RequestContext(request),
    )


@login_required
def add(request):
    """
    Add a new cluster
    """
    if request.method == 'POST':
        form = AddClusterForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            hostname = data['hostname']
            slug = data['slug']
            port = data['port']
            username = data['username']
            password = data['password']
            try:
                cluster = Cluster(hostname=hostname, slug=slug, port=port, \
                                  username=username, password=password)
                cluster.save()
                cluster.sync_virtual_machines()
            except:
                print "Cluster not saved."
            
            return render_to_response("index.html", {
                'user': request.user,
                },
                context_instance=RequestContext(request),
            )
    else:
        form = AddClusterForm()
    return render_to_response("cluster/add.html", {
        'form': form,
        'user': request.user,
        },
        context_instance=RequestContext(request),
    )


@login_required
def list(request):
    """
    List all clusters
    """
    cluster_list = Cluster.objects.all()
    return render_to_response("cluster/list.html", {
        'cluster_list': cluster_list,
        'user': request.user,
        },
        context_instance=RequestContext(request),
    )


@login_required
def edit(request, cluster_slug):
    """
    Edit a cluster
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    return render_to_response("cluster/edit.html", {
        'cluster': cluster,
        'user': request.user,
        },
        context_instance=RequestContext(request),
    )


@login_required
def permissions(request, cluster_slug, user_id=None, group_id=None):
    """
    Update a users permissions.
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    user = request.user
    if not (user.is_superuser or user.has_perm('admin', cluster)):
        return HttpResponseForbidden("You do not have sufficient privileges")
    
    if request.method == 'POST':
        form = ObjectPermissionFormNewUsers(cluster, request.POST)
        if form.is_valid():
            data = form.cleaned_data
            if form.update_perms():
                # return html to replace existing user row
                form_user = form.cleaned_data['user']
                group = form.cleaned_data['group']
                if form_user:
                    return render_to_response("cluster/user_row.html", \
                                        {'cluster':cluster, 'user':form_user})
                else:
                    return render_to_response("cluster/group_row.html", \
                                        {'cluster':cluster, 'group':group})
                
            else:
                # no permissions, send ajax response to remove user
                return HttpResponse('0', mimetype='application/json')
        
        # error in form return ajax response
        content = json.dumps(form.errors)
        return HttpResponse(content, mimetype='application/json')

    if user_id:
        form_user = get_object_or_404(User, id=user_id)
        data = {'permissions':get_user_perms(form_user, cluster), \
                'user':user_id}
    elif group_id:
        group = get_object_or_404(UserGroup, id=group_id)
        data = {'permissions':get_group_perms(group, cluster), \
                'group':group_id}
    else:
        data = {}
    form = ObjectPermissionFormNewUsers(cluster, data)
    return render_to_response("cluster/permissions.html", \
                {'form':form, 'cluster':cluster, 'user_id':user_id, \
                'group_id':group_id}, \
               context_instance=RequestContext(request))


class QuotaForm(forms.Form):
    """
    Form for editing user quota on a cluster
    """
    input = forms.TextInput(attrs={'size':5})
    
    user = forms.ModelChoiceField(queryset=ClusterUser.objects.all(), \
                                  widget=forms.HiddenInput)
    ram = forms.IntegerField(label='Memory (MB)', required=False, min_value=0, \
                             widget=input)
    virtual_cpus = forms.IntegerField(label='Virtual CPUs', required=False, \
                                    min_value=0, widget=input)
    disk = forms.IntegerField(label='Disk Space (MB)', required=False, \
                              min_value=0, widget=input)
    delete = forms.BooleanField(required=False, widget=forms.HiddenInput)


@login_required
def quota(request, cluster_slug, user_id):
    """
    Updates quota for a user
    """
    cluster = get_object_or_404(Cluster, slug=cluster_slug)
    user = request.user
    if not (user.is_superuser or user.has_perm('admin', cluster)):
        return HttpResponseForbidden("You do not have sufficient privileges")
    
    if request.method == 'POST':
        form = QuotaForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            cluster_user = data['user']
            data = None if data['delete'] else data
            cluster.set_quota(cluster_user, data)
            
            # return updated html
            cluster_user = cluster_user.cast()
            if isinstance(cluster_user, (Profile,)):
                return render_to_response("cluster/user_row.html",
                        {'cluster':cluster, 'user':cluster_user.user})
            else:
                return render_to_response("cluster/group_row.html",
                        {'cluster':cluster, 'group':cluster_user.user_group})
        
        # error in form return ajax response
        content = json.dumps(form.errors)
        return HttpResponse(content, mimetype='application/json')
    
    if user_id:
        cluster_user = get_object_or_404(ClusterUser, id=user_id)
        quota = cluster.get_quota(cluster_user)
        data = {'user':user_id}
        if quota:
            data.update(quota)
    else:
        return HttpResponseNotFound('User was not found')
    
    form = QuotaForm(data)
    return render_to_response("cluster/quota.html", \
                        {'form':form, 'cluster':cluster, 'user_id':user_id}, \
                        context_instance=RequestContext(request))


class AddClusterForm(forms.Form):
        hostname = forms.CharField(label='Hostname', max_length='256')
        slug = forms.CharField(label='Slug', max_length=150)
        port = forms.IntegerField(label='Port', initial='5080')
        username = forms.CharField(label='Username', required=False)
        password = forms.CharField(label='Password', required=False)