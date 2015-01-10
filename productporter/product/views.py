#!/bin/env python
# -*- coding: utf-8 -*-
"""
    productporter.product.views
    ~~~~~~~~~~~~~~~~~~~~~~~~~

    product blueprint

    :copyright: (c) 2014 by the ProductPorter Team.
    :license: BSD, see LICENSE for more details.
"""
import datetime
import json
from flask import Blueprint, request, current_app, flash, redirect, \
    url_for, jsonify, make_response
from flask.ext.login import current_user
from qiniu import Auth


from productporter.product.phapi import ProductHuntAPI
from productporter.product.models import Product, Tag
from productporter.utils.helper import render_template, pull_and_save_posts, render_markup, \
    query_products, can_translate, can_review, is_online
from productporter.utils.decorators import moderator_required
from productporter.user.models import User

product = Blueprint('product', __name__)

def _tag_names(post):
    """return tag names of this post"""

    tagnames = []
    for tag in post.tags:
        if len(tagnames) == 0:
            tagnames.append(tag.name)
        else:
            tagnames.append('; ' + tag.name)
    return ''.join(tagnames)

def _render_tags(post):
    """render tags. MUST BE THE SAME of macro 'render_tags' in macro.jinja.html"""
    tag_template = '<a class="label label-default" href="%s">%s</a>'
    tag_html = []
    for tag in post.tags:
        tag_html.append(tag_template % \
            (url_for('product.tags', tag=tag.name), tag.name))
    tag_html.append('<br/><br/>')
    return '\n'.join(tag_html)

def _render_contributors(contributers, postid, locked_by, field):
    """render contributors, MUST BE THE SAME of macro 'contributors' in macro.jinja.html"""
    div_template = "<div class='translaters-list' data-postid='%s' field='%s'>edit by %s</div>"
    user_template = "<a href='%s'>@%s</a>"
    user_htmls = []
    users = contributers.all()
    for user in users:
        nickname = user.nickname if user.nickname else user.username
        user_htmls.append(user_template % \
            (url_for('user.profile', username=user.username), nickname))
    if locked_by:
        nickname = locked_by.nickname if locked_by.nickname else locked_by.username
        user_htmls.append((' - locked by ' + user_template) % \
            (url_for('user.profile', username=locked_by.username), nickname))
    return div_template % (postid, field, '\n'.join(user_htmls))

def _post_aquire_translate(request):
    """aquire to translate post"""
    postid = request.args.get('postid')
    field = request.args.get('field', 'ctagline')

    current_app.logger.info('aquire translate %s for post %s' % (field, str(postid)))
    if not can_translate(current_user):
        ret = {
            'status': 'error',
            'postid': postid,
            'error': 'Please sign in first'
            }
        return make_response(jsonify(**ret), 401)

    post = Product.query.filter(Product.postid==postid).first_or_404()
    if getattr(post, field + '_locked'):
        ret = {
            'status': 'error',
            'postid': postid,
            'error': '%s is locked. Please contact adminitrator.'
            }
        return make_response(jsonify(**ret), 403)

    editing_user = getattr(post, 'editing_' + field + '_user')
    if (editing_user) and \
        (editing_user.username != current_user.username) and \
        (is_online(editing_user)):
        ret = {
            'status': 'error',
            'postid': post.postid,
            'error': '%s is editing by %s' % \
                (field, editing_user.username)
            }
        return make_response(jsonify(**ret), 400)

    setattr(post, 'editing_' + field + '_user_id', current_user.id)
    post.save()
    ret = {
            'status': 'success',
            'postid': post.postid,
            'field': field,
            'value': getattr(post, field),
            'tags': _tag_names(post)
        }
    return jsonify(**ret)

# translate detail
@product.route('/translate', methods=["GET", "PUT", "POST"])
def translate():
    """
    use GET to aquire translation
    use PUT/POST to commit translation

    :param postid: The postid of product
    :param field: The field of operation, could be 'ctagline' or 'cintro'
    :param value: The value of translate field
    """
    if request.method == 'GET':
        return _post_aquire_translate(request)

    jsondata = None
    try:
        jsondata = json.loads(request.data)
    except ValueError:
        ret = {
            'status': 'error',
            'message': "invalid json data"
        }
        return make_response(jsonify(**ret), 405)

    postid = jsondata['postid']
    field = jsondata['field']

    if not can_translate(current_user):
        ret = {
            'status': 'error',
            'postid': postid,
            'field': field,
            'error': 'Please sign in first'
            }
        return make_response(jsonify(**ret), 401)

    post = Product.query.filter(Product.postid==postid).first_or_404()

    try:
        canceled = jsondata['canceled']
        if canceled:
            setattr(post, 'editing_' + field + '_user_id', None)
            post.save()
            ret = {
                'status': 'success',
                'postid': post.postid,
                'field': field
                }
            return jsonify(**ret)
    except KeyError:
        pass

    current_app.logger.info('commit %s for post %s' % (field, str(postid)))

    # deal with tags
    if field == 'ctagline':
        post.set_tags(jsondata['tags'])
    # deal with other filed data
    setattr(post, field, jsondata['value'])
    setattr(post, 'editing_' + field + '_user_id', None)
    post.save()
    getattr(current_user, 'add_' + field + '_product')(post)
    ret = {
        'status': 'success',
        'postid': post.postid,
        'field': field,
        'value': render_markup(getattr(post, field)),
        'contributors': _render_contributors( \
            getattr(post, field + '_editors'), post.postid, \
            getattr(post, field + '_locked_user'), field),
        'tags': _render_tags(post)
    }

    return jsonify(**ret)

# posts list
@product.route('/', methods=["GET"])
def index():
    """ product posts home dashboard """
    return redirect(url_for('product.posts'))

# posts list
@product.route('/posts/', methods=["GET"])
def posts():
    """ product posts home dashboard """
    spec_day = request.args.get('day', '')
    day, posts = query_products(spec_day)
    post_count = len(posts)
    tags = Tag.names()
    return render_template('product/posts.jinja.html',
        post_count=post_count, posts=posts, day=day, tags=tags)

# posts list
@product.route('/posts/<postid>', methods=["GET"])
def post_intro(postid):
    """ product detail information page """

    post = Product.query.filter(Product.postid==postid).first_or_404()
    tags = Tag.names()
    return render_template('product/post_intro.jinja.html', post=post, tags=tags)

#pull products
@product.route('/pull')
def pull():
    """ pull data from producthunt.com """
    day = request.args.get('day', '')
    count = pull_and_save_posts(day)
    return "pulled %d posts " % (count)

@product.route('/lock', methods=['GET'])
@moderator_required
def lock():
    """
    lock product

    :param postid: The postid of product
    :param op: Operation, clould be 'lock' or 'unlock'
    :param field: Field, could be 'ctagline' or 'cintro'
    """
    postid = request.args.get('postid', '')
    op = request.args.get('op', 'lock')
    field = request.args.get('field', 'ctagline')
    post = Product.query.filter(Product.postid==postid).first_or_404()

    if op.lower() == 'lock':
        setattr(post, field + '_locked', True)
        setattr(post, field + '_locked_user_id', current_user.id)
        op = 'Unlock'
    else:
        setattr(post, field + '_locked', False)
        setattr(post, field + '_locked_user_id', None)
        op = 'Lock'
    post.save()
    ret = {
        'status': 'success',
        'postid': post.postid,
        'contributors': _render_contributors( \
            getattr(post, field + '_editors'), post.postid, \
            getattr(post, field + '_locked_user'), field)
    }
    return jsonify(**ret)

@product.route('/tags/', methods=["GET"])
def tags():
    """show all products"""
    return "under construction"

@product.route('/tags/<tagname>', methods=["GET"])
def tags_name(tagname):
    """show all products by selected tag"""
    return "under construction"

@product.route('/dailybriefing/<day>', methods=['GET'])
@moderator_required
def dailybriefing(day):
    """ Generate daily briefing """
    qday, posts = query_products(day)
    post_count = len(posts)

    # Thanks to contributors
    editors = []
    for post in posts:
        if post.ctagline and post.ctagline_locked:
            editors += post.ctagline_editors
    # Thank once is enough
    editors = {}.fromkeys(editors).keys()

    return render_template('product/dailybriefing.jinja.html',
        post_count=post_count, posts=posts, day=qday, editors=editors)

@product.route('/qiniutoken', methods=['GET'])
def get_qiniu_token():
    q = Auth(current_app.config["QINIU_ACCESS_KEY"], current_app.config["QINIU_SECRET_KEY"])
    token = q.upload_token(current_app.config["QINIU_BUCKET"])
    ret = {'uptoken': token}
    return jsonify(**ret)

