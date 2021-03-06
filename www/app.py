#!/usr/bin/env python3
# _*_ coding:utf-8 _*_

import logging;
import orm
from handlers import COOKIE_NAME, cookie2user
from jinja2 import Environment, FileSystemLoader
logging.basicConfig(level=logging.INFO)
import asyncio,os,json,time
from datetime import datetime

from aiohttp import web
from coroweb import add_routes,add_static
from config import configs

def init_jinja2(app,**kw):
    logging.info('init jinja2...')
    options=dict(
        autoescape=kw.get('autoescape',True),
        block_start_string=kw.get('block_start_string','{%'),
        block_end_string=kw.get('block_end_string','%}'),
        variable_start_string=kw.get('variable_start_string','{{'),
        variable_end_string=kw.get('variable_end_string','}}'),
        auto_reload=kw.get('auto_reload',True)
    )
    path=kw.get('path',None)
    if path is None:
        path=os.path.join(os.path.dirname(os.path.abspath(__file__)),'templates')
    logging.info('set jinja2 template path: %s'% path)
    env=Environment(loader=FileSystemLoader(path),**options)
    filters=kw.get('filters',None)
    if filters is not None:
        for name ,f in filters.items():
            env.filters[name]=f
    app['__templating__']=env

# middlewares 过滤器----------------

@asyncio.coroutine
def logger_factory(app,handler):
    @asyncio.coroutine
    def logger(request):
        logging.info('Request:%s %s'%(request.method,request.path))
        return (yield from handler(request))
    return logger


@asyncio.coroutine
def auth_factory(app,handler):
    @asyncio.coroutine
    def auth(request):
        logging.info('check user:%s %s'%(request.method,request.path))
        request.__user__=None
        cookie_str=request.cookies.get(COOKIE_NAME)
        if cookie_str:
            user=yield from cookie2user(cookie_str)
            if user:
                logging.info('set current user:%s'% user.email)
                request.__user__=user
        # cookie 验证失败 则跳转到 登陆页面
        if request.path.startswith('/manage/') and (request.__user__ is None or not request.__user__.admin):
            return web.HTTPFound('/signin')
        return (yield from handler(request))
    return auth


#
#
@asyncio.coroutine
def response_factory(app,handler):
    @asyncio.coroutine
    def response(request):
        logging.info('Response handler...')
        r=yield from handler(request)
        if isinstance(r,web.StreamResponse):
            return r
        if isinstance(r,bytes):
            resp=web.Response(body=r)
            resp.content_type='application/octet-stream'
            return resp
        if isinstance(r,str):
            print("111")
            if r.startswith('redirect:'):
                return web.HTTPFound(r[9:])
            resp=web.Response(body=r.encode('utf-8'))
            resp.content_type='text/html;charset=utf-8'
            return resp
        if isinstance(r,dict):
            template=r.get('__template__')
            if template is None:
                resp=web.Response(body=json.dumps(r,ensure_ascii=False,default=lambda o:o.__dict__).encode('utf-8'))
                resp.content_type='application/json;charset=utf-8'
                return resp
            else:
                r['__user__']=request.__user__
                resp=web.Response(body=app['__templating__'].get_template(template).render(**r).encode('utf-8'))
                resp.content_type='text/html;charset=utf-8'
                return resp
        if isinstance(r,int) and r>=100 and r<600:
            return web.Response(r)
        if isinstance(r,tuple) and len(r)==2:
            t,m=r
            if isinstance(t,int) and t>=100 and t<600:
                return web.Response(t,str(m))
        resp=web.Response(body=str(r).encode('utf-8'))
        resp.content_type='text/plain;charset=utf-8'
        return resp
    return response

#
# jinja2 时间过滤器
def datetime_filter(t):
    delta=int(time.time()-t)
    if delta<60:
        return u'1分钟前'
    if delta<3600:
        return u'%s分钟前'%(delta//60)
    if delta<86400:
        return u'%s小时前'%(delta//3600)
    if delta<604800:
        return u'%s天前'%(delta//86400)
    dt=datetime.fromtimestamp(t)
    return u'%s年%s月%s日'%(dt.year,dt.month,dt.day)

@asyncio.coroutine
def init(loop):
    yield from orm.create_pool(loop=loop,
                               host=configs.db.host,
                               port=configs.db.port,
                               user=configs.db.user,
                               password=configs.db.password,
                               database=configs.db.database)
    app=web.Application(loop=loop,middlewares=[logger_factory,auth_factory,response_factory])

    # 这里给 jinja2 加上一个时间过滤器，因为返回来的时间是时间戳浮点数
    init_jinja2(app,filters=dict(datetime=datetime_filter))
    add_routes(app,'handlers')
    add_routes(app,'bqw_api.bqw_handlers')
    add_static(app)
    port=9000
    ip="0.0.0.0"
    srv=yield from loop.create_server(app.make_handler(),ip,port)
    logging.info('server started at http://127.0.0.1:%s',port)
    return srv


if(__name__=='__main__'):
    loop=asyncio.get_event_loop()
    loop.run_until_complete(init(loop))
    loop.run_forever()

