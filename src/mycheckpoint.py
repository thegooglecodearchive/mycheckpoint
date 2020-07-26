#!/usr/bin/python

#
# mycheckpoint: Lightweight, SQL oriented monitoring solution for MySQL
#
# Released under the BSD license
#
# Copyright (c) 2009-2013, Shlomi Noach
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met:
#
#     * Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer.
#     * Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution.
#     * Neither the name of the organization nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#

import ConfigParser
import fcntl
import getpass
import MySQLdb
import os
import re
import sys
import socket
import time
import traceback
import warnings
from optparse import OptionParser
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

import smtplib
try:
    MIMEText = __import__("email.mime.text", globals(), locals(), ["MIMEText"]).MIMEText
    MIMEMultipart = __import__("email.mime.multipart", globals(), locals(), ["MIMEMultipart"]).MIMEMultipart
except:
    try:
        MIMEText = __import__("email.MIMEText", globals(), locals(), ["MIMEText"]).MIMEText
        MIMEMultipart = __import__("email.MIMEMultipart", globals(), locals(), ["MIMEMultipart"]).MIMEMultipart
    except:
        pass



def parse_options():
    global options
    global args
    
    usage = """usage: mycheckpoint [options] [command [, command ...]]

See online documentation on http://code.openark.org/forge/mycheckpoint/documentation

Available commands:
  http
  deploy
  email_brief_report
  email_alert_pending_report
    """
    parser = OptionParser(usage=usage)
    parser.add_option("-u", "--user", dest="user", help="MySQL user")
    parser.add_option("-H", "--host", dest="host", help="MySQL host. Written to by this application (default: localhost)")
    parser.add_option("-p", "--password", dest="password", help="MySQL password")
    parser.add_option("--ask-pass", action="store_true", dest="prompt_password", help="Prompt for password")
    parser.add_option("-P", "--port", dest="port", type="int", help="TCP/IP port (default: 3306)")
    parser.add_option("-S", "--socket", dest="socket", help="MySQL socket file. Only applies when host is localhost (default: /var/run/mysqld/mysql.sock)")
    parser.add_option("", "--monitored-host", dest="monitored_host", help="MySQL monitored host. Specity this when the host you're monitoring is not the same one you're writing to (default: none, host specified by --host is both monitored and written to)")
    parser.add_option("", "--monitored-port", dest="monitored_port", type="int", help="Monitored host's TCP/IP port (default: 3306). Only applies when monitored-host is specified")
    parser.add_option("", "--monitored-socket", dest="monitored_socket", help="Monitored host MySQL socket file. Only applies when monitored-host is specified and is localhost (default: /var/run/mysqld/mysql.sock)")
    parser.add_option("", "--monitored-user", dest="monitored_user", help="MySQL monitored server user name. Only applies when monitored-host is specified (default: same as user)")
    parser.add_option("", "--monitored-password", dest="monitored_password", help="MySQL monitored server password. Only applies when monitored-host is specified (default: same as password)")
    parser.add_option("", "--defaults-file", dest="defaults_file", help="Read from MySQL configuration file. Overrides all other options")
    parser.add_option("-d", "--database", dest="database", help="Database name (required unless query uses fully qualified table names)")
    parser.add_option("", "--skip-aggregation", dest="skip_aggregation", action="store_true", default=False, help="Skip creating and maintaining aggregation tables")
    parser.add_option("", "--rebuild-aggregation", dest="rebuild_aggregation", action="store_true", default=False, help="Completely rebuild (drop, create and populate) aggregation tables upon deploy")
    parser.add_option("", "--purge-days", dest="purge_days", type="int", help="Purge data older than specified amount of days (default: 182)")
    parser.add_option("", "--disable-bin-log", dest="disable_bin_log", action="store_true", help="Disable binary logging (binary logging enabled by default)")
    parser.add_option("", "--skip-disable-bin-log", dest="disable_bin_log", action="store_false", help="Skip disabling the binary logging (this is default behaviour; binary logging enabled by default)")
    parser.add_option("", "--skip-check-replication", dest="skip_check_replication", action="store_true", help="Skip checking on main/subordinate status variables")
    parser.add_option("-o", "--force-os-monitoring", dest="force_os_monitoring", action="store_true", help="Monitor OS even if monitored host does does nto appear to be the local host. Use when you are certain the monitored host is local")
    parser.add_option("", "--skip-alerts", dest="skip_alerts", action="store_true", help="Skip evaluating alert conditions as well as sending email notifications")
    parser.add_option("", "--skip-emails", dest="skip_emails", action="store_true", help="Skip sending email notifications")
    parser.add_option("", "--force-emails", dest="force_emails", action="store_true", help="Force sending email notifications even if there's nothing wrong")
    parser.add_option("", "--skip-custom", dest="skip_custom", action="store_true", help="Skip custom query execution and evaluation")
    parser.add_option("", "--skip-defaults-file", dest="skip_defaults_file", action="store_true", help="Do not read defaults file. Overrides --defaults-file and ignores /etc/mycheckpoint.cnf")
    parser.add_option("", "--chart-width", dest="chart_width", type="int", help="Chart image width (default: 370, min value: 150)")
    parser.add_option("", "--chart-height", dest="chart_height", type="int", help="Chart image height (default: 180, min value: 100)")
    parser.add_option("", "--chart-service-url", dest="chart_service_url", help="Url to Google charts API (default: http://chart.apis.google.com/chart)")
    parser.add_option("", "--smtp-host", dest="smtp_host", help="SMTP mail server host name or IP")
    parser.add_option("", "--smtp-from", dest="smtp_from", help="Address to use as mail sender")
    parser.add_option("", "--smtp-to", dest="smtp_to", help="Comma delimited email addresses to send emails to")
    parser.add_option("", "--run-as-service", dest="run_as_service", action="store_true", help="Hint to this script that it is being executed as a linux service.")
    parser.add_option("", "--allow-http-as-service", dest="allow_http_as_service", action="store_true", help="Must be provided in order for mycheckpoint to be able to open HTTP when executed with '--run-as-service'")
    parser.add_option("", "--http-port", dest="http_port", type="int", help="Socket to listen on when running as web server (argument is http)")
    parser.add_option("", "--single", dest="single", action="store_true", help="Only allow one running instance of mycheckpoint at a time on this machine")
    parser.add_option("", "--debug", dest="debug", action="store_true", help="Print stack trace on error")
    parser.add_option("-v", "--verbose", dest="verbose", action="store_true", help="Print user friendly messages")
    parser.add_option("", "--version", dest="version", action="store_true", help="Prompt version number")
    options, args = parser.parse_args()

    option_types = {}
    for option in parser.option_list:
        option_types[option.dest] = option.type
        
    option_defaults = {
        "user": "",
        "host": "localhost",
        "password": "",
        "prompt_password": False,
        "port": 3306,
        "socket": "/var/run/mysqld/mysql.sock",
        "monitored_host": None,
        "monitored_port": 3306,
        "monitored_socket": None,
        "monitored_user": None,
        "monitored_password": None,
        "defaults_file": "",
        "database": "mycheckpoint",
        "skip_aggregation": False,
        "rebuild_aggregation": False,
        "purge_days": 182,
        "disable_bin_log": False,
        "skip_check_replication": False,
        "force_os_monitoring": False,
        "skip_alerts": False,
        "skip_emails": False,
        "force_emails": False,
        "skip_custom": False,
        "skip_defaults_file": False,
        "chart_width": 370,
        "chart_height": 180,
        "chart_service_url": "http://chart.apis.google.com/chart",
        "smtp_host": None,
        "smtp_from": None,
        "smtp_to": None,
        "run_as_service": False,
        "allow_http_as_service": False,
        "http_port": 12306,
        "single": False,
        "debug": False,
        "verbose": False,
        "version": False,
        }
    
    # Determine defaults file name:
    default_defaults_file_name = "/etc/mycheckpoint.cnf" 
    if not options.defaults_file:
        if os.path.exists(default_defaults_file_name):
            options.defaults_file = default_defaults_file_name
    if options.skip_defaults_file:
        options.defaults_file = None
    if options.defaults_file:
        verbose("Using %s as defaults file" % options.defaults_file)
    if options.defaults_file:
        # Apply config-file options that do not appear on command line:
        # 'defaults_file' and 'verbose' are options that cannot be overwritten since they're already read beforehand
        config = ConfigParser.ConfigParser()
        config.read([options.defaults_file])
        valid_sections = [section for section in config.sections() if section in ["client", "mycheckpoint"]]
        for section in valid_sections:
            for option_dest in config.options(section):
                if options.__dict__.has_key(option_dest):
                    # A known option
                    if options.__dict__[option_dest]:
                        # Option value specified on command line. Do nothing! 
                        # Command line take precedence
                        pass
                    else:
                        option_value = config.get(section, option_dest)
                        if option_types[option_dest] == "int":
                            option_value = int(option_value)
                        options.__dict__[option_dest] = option_value
                        
    # Apply default values for options not specified on command line nor config file: 
    for option_dest in options.__dict__.keys():
        if options.__dict__[option_dest] is None:
            options.__dict__[option_dest] = option_defaults[option_dest]
    
    return options, args


def verbose(message, force_verbose=False):
    if options.verbose or force_verbose:
        print "-- %s" % message


def print_error(message):
    sys.stderr.write("-- ERROR: %s\n" % message)
    return None


def sorted_list(l):
    """
    In favor of Python 2.3 users. Be strong!
    """
    result = []
    result.extend(l)
    result.sort()
    return result
    

def open_connections():
    if options.prompt_password:
        password=getpass.getpass()
    else:
        password=options.password
    write_connection = MySQLdb.connect(
        host = options.host,
        user = options.user,
        passwd = password,
        port = options.port,
        unix_socket = options.socket,
        db = database_name)

    # If no read (monitored) host specified, then read+write hosts are the same one...
    if not options.monitored_host:
        return write_connection, write_connection;

    verbose("monitored host is: %s" % options.monitored_host)
    
    if not options.monitored_user:
        options.monitored_user = options.user
        options.monitored_password = options.password
        verbose("monitored host credentials undefined; using write host credentials")
    if not options.monitored_socket:
        options.monitored_socket = options.socket

    # Need to open a read connection
    monitored_connection = MySQLdb.connect(
        user = options.monitored_user,
        passwd = options.monitored_password,
        host = options.monitored_host,
        port = options.monitored_port,
        unix_socket = options.monitored_socket)

    return monitored_connection, write_connection;


def init_connections():
    queries = [
               """SET @@group_concat_max_len = GREATEST(@@group_concat_max_len, @@max_allowed_packet)""",
               """SET @@session.sql_mode := REPLACE(@@session.sql_mode, 'ONLY_FULL_GROUP_BY', '')"""
            ]
    for query in queries:
        act_query(query, monitored_conn)
        act_query(query, write_conn)


def act_query(query, connection=None):
    """
    Run the given query, commit changes
    """
    if connection is None:
        connection = write_conn
    connection = write_conn
    cursor = connection.cursor()
    num_affected_rows = cursor.execute(query)
    cursor.close()
    connection.commit()
    return num_affected_rows


def act_query_ignore_error(query, connection=None):
    """
    Run the given query, ignore error silently
    """
    try:
        return act_query(query, connection)
    except MySQLdb.Error:
        if options.debug:
            traceback.print_exc()
        return -1
    

def get_row(query, connection=None):
    if connection is None:
        connection = monitored_conn
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(query)
    row = cursor.fetchone()

    cursor.close()
    return row


def get_rows(query, connection=None):
    if connection is None:
        connection = monitored_conn
    cursor = connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute(query)
    rows = cursor.fetchall()

    cursor.close()
    return rows


def get_last_insert_id():
    query = "SELECT LAST_INSERT_ID() AS id"
    row = get_row(query, write_conn)
    return int(row["id"])


def get_last_written_timestamp():
    query = """
            SELECT 
              CONCAT(ts, '') AS ts_as_string 
            FROM 
              %s.%s
            WHERE 
              id = %d
        """ % (database_name, table_name, status_variables_insert_id)

    row = get_row(query, write_conn)
    return row["ts_as_string"]


def get_current_timestamp():
    query = "SELECT CURRENT_TIMESTAMP() AS current_ts"
    row = get_row(query, write_conn)
    return row["current_ts"]


def prompt_deploy_instructions():
    print "--"
    print "-- Make sure `%s` schema exists, e.g." % database_name
    print "--   CREATE DATABASE `%s`" % database_name
    print "-- Make sure the user has ALL PRIVILEGES on the `%s` schema. e.g." % database_name
    print "--   GRANT ALL ON `%s`.* TO 'my_user'@'my_host' IDENTIFIED BY 'my_password'" % database_name
    print "-- The user will have to have the SUPER privilege in order to disable binary logging"
    print "-- - Otherwise, use --skip-disable-bin-log (but then be aware that subordinates replicate this server's status)"
    print "-- In order to read main and subordinate status, the user must also be granted with REPLICATION CLIENT or SUPER privileges"
    print "-- - Otherwise, use --skip-check-replication"
    print "--"


def prompt_collect_instructions():
    print "--"
    print "-- Re-execute with --verbose --debug for detailed message and stack trace."
    print "--"


openark_lchart="""
    openark_lchart=function(a,b){if(a.style.width==""){this.canvas_width=b.width}else{this.canvas_width=a.style.width}if(a.style.height==""){this.canvas_height=b.height}else{this.canvas_height=a.style.height}this.title_height=0;this.chart_title="";this.x_axis_values_height=20;this.y_axis_values_width=50;this.y_axis_tick_values=[];this.y_axis_tick_positions=[];this.x_axis_grid_positions=[];this.x_axis_label_positions=[];this.x_axis_labels=[];this.y_axis_min=0;this.y_axis_max=0;this.y_axis_round_digits=0;this.multi_series=[];this.multi_series_dot_positions=[];this.series_invisibility=[];this.series_labels=[];this.series_legend_values=[];this.timestamp_legend_value=null;this.series_colors=openark_lchart.series_colors;this.tsstart=null;this.tsstep=null;this.container=a;this.isIE=false;this.current_color=null;this.skip_interactive=false;if(b.skipInteractive){this.skip_interactive=true}this.square_lines=false;if(b.squareLines){this.square_lines=true}this.recalc();return this};openark_lchart.title_font_size=10;openark_lchart.title_color="#505050";openark_lchart.axis_color="#707070";openark_lchart.axis_font_size=8;openark_lchart.min_x_label_spacing=32;openark_lchart.legend_font_size=9;openark_lchart.legend_color="#606060";openark_lchart.legend_invisible_color="#b0b0b0";openark_lchart.series_line_width=1.5;openark_lchart.grid_color="#e4e4e4";openark_lchart.grid_thick_color="#c8c8c8";openark_lchart.position_pointer_color="#808080";openark_lchart.series_colors=["#ff0000","#ff8c00","#4682b4","#9acd32","#dc143c","#9932cc","#ffd700","#191970","#7fffd4","#808080","#dda0dd"];openark_lchart.google_simple_format_scheme="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";openark_lchart.prototype.create_graphics=function(){this.interactive_legend=null;this.legend_values_containers=[];this.timestamp_value_container=null;this.canvas_shadow=null;this.position_pointer=null;this.container.innerHTML="";this.isIE=(/MSIE/.test(navigator.userAgent)&&!window.opera);this.container.style.position="relative";this.container.style.color=""+openark_lchart.axis_color;this.container.style.fontSize=""+openark_lchart.axis_font_size+"pt";this.container.style.fontFamily="Helvetica,Verdana,Arial,sans-serif";if(!this.skip_interactive){var b=this;this.container.onmousemove=function(c){b.on_mouse_move(c)};this.container.onmouseout=function(c){b.on_mouse_out(c)}}if(this.isIE){}else{var a=document.createElement("canvas");a.setAttribute("width",this.canvas_width);a.setAttribute("height",this.canvas_height);this.canvas=a;this.container.appendChild(this.canvas);this.ctx=this.canvas.getContext("2d")}this.canvas_shadow=document.createElement("div");this.canvas_shadow.style.position="absolute";this.canvas_shadow.style.top="0";this.canvas_shadow.style.left="0";this.canvas_shadow.style.width=this.canvas_width;this.canvas_shadow.style.height=this.canvas_height;this.container.appendChild(this.canvas_shadow)};openark_lchart.prototype.parse_url=function(a){a=a.replace(/[+]/gi," ");var b={};var c=a.indexOf("?");if(c>=0){a=a.substring(c+1)}tokens=a.split("&");for(i=0;i<tokens.length;++i){param_tokens=tokens[i].split("=");if(param_tokens.length==2){b[param_tokens[0]]=param_tokens[1]}}return b};openark_lchart.prototype.recalc=function(){this.chart_width=this.canvas_width-this.y_axis_values_width;this.chart_height=this.canvas_height-(this.x_axis_values_height+this.title_height);this.chart_origin_x=this.canvas_width-this.chart_width;this.chart_origin_y=this.title_height+this.chart_height;this.y_axis_tick_values=[];this.y_axis_tick_positions=[];if(this.y_axis_max<=this.y_axis_min){return}max_steps=Math.floor(this.chart_height/(openark_lchart.axis_font_size*1.6));round_steps_basis=[1,2,5];step_size=null;pow=0;for(power=-4;power<10&&!step_size;++power){for(i=0;i<round_steps_basis.length&&!step_size;++i){round_step=round_steps_basis[i]*Math.pow(10,power);if((this.y_axis_max-this.y_axis_min)/round_step<max_steps){step_size=round_step;pow=power}}}var c=step_size*Math.ceil(this.y_axis_min/step_size);while(c<=this.y_axis_max){var b=(pow>=0?c:c.toFixed(-pow));this.y_axis_tick_values.push(b);var a=(c-this.y_axis_min)/(this.y_axis_max-this.y_axis_min);this.y_axis_tick_positions.push(Math.floor(this.chart_origin_y-a*this.chart_height));c+=step_size}this.y_axis_round_digits=(pow>=0?0:-pow)};openark_lchart.prototype.read_google_url=function(f){params=this.parse_url(f);this.title_height=0;if(params.chtt){this.chart_title=params.chtt;this.title_height=20}if(params.chdl){var j=params.chdl.split("|");this.series_labels=j}if(params.chco){var j=params.chco.split(",");this.series_colors=new Array(j.length);for(i=0;i<j.length;++i){this.series_colors[i]="#"+j[i]}}var j=params.chxr.split(",");if(j.length>=3){this.y_axis_min=parseFloat(j[1]);this.y_axis_max=parseFloat(j[2])}this.recalc();var j=params.chg.split(",");if(j.length>=6){var t=parseFloat(j[0]);var k=parseFloat(j[4]);this.x_axis_grid_positions=[];for(i=0,chart_x_pos=0;chart_x_pos<this.chart_width;++i){chart_x_pos=(k+i*t)*this.chart_width/100;if(chart_x_pos<this.chart_width){this.x_axis_grid_positions.push(Math.floor(chart_x_pos+this.chart_origin_x))}}}var j=params.chxp.split("|");for(axis=0;axis<j.length;++axis){var n=j[axis].split(",");var e=parseInt(n[0]);if(e==0){this.x_axis_label_positions=new Array(n.length-1);for(i=1;i<n.length;++i){var l=parseFloat(n[i])*this.chart_width/100;this.x_axis_label_positions[i-1]=Math.floor(l+this.chart_origin_x)}}}var j=params.chxl.split("|");if(j[0]=="0:"){this.x_axis_labels=new Array(j.length-1);for(i=1;i<j.length;++i){this.x_axis_labels[i-1]=j[i]}}if(params.chd){var a=params.chd;var g=null;var d=a.substring(0,2);if(d=="s:"){g="simple"}else{if(d=="t:"){g="text"}}if(g){this.multi_series=[];this.multi_series_dot_positions=[]}if(g=="simple"){this.skip_interactive=true;a=a.substring(2);var j=a.split(",");this.multi_series=new Array(j.length);this.multi_series_dot_positions=new Array(j.length);for(series_index=0;series_index<j.length;++series_index){var c=j[series_index];var h=new Array(c.length);var r=new Array(c.length);for(i=0;i<c.length;++i){var s=c.charAt(i);if(s=="_"){h[i]=null;r[i]=null}else{var m=openark_lchart.google_simple_format_scheme.indexOf(s)/61;var b=this.y_axis_min+m*(this.y_axis_max-this.y_axis_min);h[i]=b;r[i]=Math.round(this.chart_origin_y-m*this.chart_height)}}this.multi_series[series_index]=h;this.multi_series_dot_positions[series_index]=r}}if(g=="text"){a=a.substring(2);var j=a.split("|");this.multi_series=new Array(j.length);this.multi_series_dot_positions=new Array(j.length);for(series_index=0;series_index<j.length;++series_index){var q=j[series_index];var o=q.split(",");var h=new Array(o.length);var r=new Array(o.length);for(i=0;i<o.length;++i){var p=o[i];if(p=="_"){h[i]=null;r[i]=null}else{h[i]=parseFloat(p);var m=0;if(this.y_axis_max>this.y_axis_min){if(h[i]<this.y_axis_min){m=0}else{if(h[i]>this.y_axis_max){m=1}else{m=(h[i]-this.y_axis_min)/(this.y_axis_max-this.y_axis_min)}}}r[i]=Math.round(this.chart_origin_y-m*this.chart_height)}}this.multi_series[series_index]=h;this.multi_series_dot_positions[series_index]=r}}}if(params.tsstart){tsstart_text=params.tsstart.replace(/-/g,"/");this.tsstart=new Date(tsstart_text)}if(params.tsstep){this.tsstep=parseInt(params.tsstep)}this.redraw()};openark_lchart.prototype.redraw=function(){this.create_graphics();this.draw()};openark_lchart.prototype.create_value_container=function(){var a=document.createElement("div");a.style.display="inline";a.style.position="absolute";a.style.right=""+0+"px";a.style.textAlign="right";a.style.fontWeight="bold";return a};openark_lchart.prototype.draw=function(){if(this.chart_title){var q={text:this.chart_title,left:0,top:0,width:this.canvas_width,height:this.title_height,text_align:"center",font_size:openark_lchart.title_font_size};if(this.chart_title.search("STALE DATA")>=0){q.background="#ffcccc"}this.draw_text(q)}this.set_color(openark_lchart.grid_color);for(i=0;i<this.y_axis_tick_positions.length;++i){this.draw_line(this.chart_origin_x,this.y_axis_tick_positions[i],this.chart_origin_x+this.chart_width-1,this.y_axis_tick_positions[i],1)}for(i=0;i<this.x_axis_grid_positions.length;++i){if(this.x_axis_labels[i].replace(/ /gi,"")){this.set_color(openark_lchart.grid_thick_color)}else{this.set_color(openark_lchart.grid_color)}this.draw_line(this.x_axis_grid_positions[i],this.chart_origin_y,this.x_axis_grid_positions[i],this.chart_origin_y-this.chart_height+1,1)}this.set_color(openark_lchart.axis_color);var n=0;for(i=0;i<this.x_axis_label_positions.length;++i){var j=this.x_axis_labels[i];var k=j.replace(/ /gi,"");if(j&&((n==0)||(this.x_axis_label_positions[i]-n>=openark_lchart.min_x_label_spacing)||!k)){this.draw_line(this.x_axis_label_positions[i],this.chart_origin_y,this.x_axis_label_positions[i],this.chart_origin_y+3,1);if(k){this.draw_text({text:""+j,left:this.x_axis_label_positions[i]-25,top:this.chart_origin_y+5,width:50,height:openark_lchart.axis_font_size,text_align:"center",font_size:openark_lchart.axis_font_size});n=this.x_axis_label_positions[i]}}}for(series=0;series<this.multi_series_dot_positions.length;++series){if(this.series_invisibility[""+series]){continue}var o=[];o.push([]);this.set_color(this.series_colors[series]);var p=this.multi_series_dot_positions[series];for(i=0;i<p.length;++i){if(p[i]==null){o.push([])}else{if(this.square_lines){var g=Math.round(this.chart_origin_x+i*this.chart_width/p.length);o[o.length-1].push({x:g,y:p[i]});g=Math.round(this.chart_origin_x+(i+1)*this.chart_width/p.length);o[o.length-1].push({x:g,y:p[i]})}else{var g=Math.round(this.chart_origin_x+i*this.chart_width/(p.length-1));o[o.length-1].push({x:g,y:p[i]})}}}for(path=0;path<o.length;++path){this.draw_line_path(o[path],openark_lchart.series_line_width)}}this.set_color(openark_lchart.axis_color);this.draw_line(this.chart_origin_x,this.chart_origin_y,this.chart_origin_x,this.chart_origin_y-this.chart_height+1,1);this.draw_line(this.chart_origin_x,this.chart_origin_y,this.chart_origin_x+this.chart_width-1,this.chart_origin_y,1);var d="";for(i=0;i<this.y_axis_tick_positions.length;++i){this.draw_line(this.chart_origin_x,this.y_axis_tick_positions[i],this.chart_origin_x-3,this.y_axis_tick_positions[i],1);this.draw_text({text:""+this.y_axis_tick_values[i],left:0,top:this.y_axis_tick_positions[i]-openark_lchart.axis_font_size+Math.floor(openark_lchart.axis_font_size/3),width:this.y_axis_values_width-5,height:openark_lchart.axis_font_size,text_align:"right",font_size:openark_lchart.axis_font_size})}if(this.series_labels&&this.series_labels.length){if(this.isIE){var m=document.createElement("div");m.style.width=this.canvas_width;m.style.height=this.canvas_height;this.container.appendChild(m)}var h=document.createElement("div");var b=document.createElement("ul");b.style.margin=0;b.style.paddingLeft=this.chart_origin_x;if(this.tsstart){var e=document.createElement("li");e.style.listStyleType="none";e.style.fontSize=""+openark_lchart.legend_font_size+"pt";e.innerHTML="&nbsp;";this.timestamp_value_container=this.create_value_container();this.timestamp_value_container.style.cursor="pointer";if(!this.skip_interactive){var l=this;this.timestamp_value_container.onclick=function(r){l.square_lines=!l.square_lines;l.redraw()}}this.timestamp_value_container.innerHTML="[type]";e.appendChild(this.timestamp_value_container);b.appendChild(e)}for(i=0;i<this.series_labels.length;++i){var e=document.createElement("li");e.style.listStyleType="square";e.style.color=this.series_colors[i];e.style.fontSize=""+openark_lchart.legend_font_size+"pt";var c=openark_lchart.legend_color;if(this.series_invisibility[""+i]){c=openark_lchart.legend_invisible_color}var a=document.createElement("span");a.className=""+i;a.style.cursor="pointer";a.style.color=c;a.innerHTML=this.series_labels[i];var l=this;a.onclick=function(r){l.series_invisibility[this.className]=!l.series_invisibility[this.className];l.redraw()};e.appendChild(a);var f=this.create_value_container();f.style.width=""+(this.chart_origin_x+32)+"px";e.appendChild(f);this.legend_values_containers.push(f);b.appendChild(e)}h.appendChild(b);this.container.appendChild(h);this.interactive_legend=document.createElement("ul");this.interactive_legend.style.position="relative";this.interactive_legend.style.right="0px";this.interactive_legend.style.top="0px";h.appendChild(this.interactive_legend)}};openark_lchart.prototype.set_color=function(a){this.current_color=a;if(!this.isIE){this.ctx.strokeStyle=a}};openark_lchart.prototype.draw_line=function(d,f,c,e,a){if(this.isIE){var b=document.createElement("v:line");b.setAttribute("from"," "+d+" "+f+" ");b.setAttribute("to"," "+c+" "+e+" ");b.setAttribute("strokecolor",""+this.current_color);b.setAttribute("strokeweight",""+a+"pt");this.container.appendChild(b)}else{this.ctx.lineWidth=a;this.ctx.strokeWidth=0.5;this.ctx.beginPath();this.ctx.moveTo(d+0.5,f+0.5);this.ctx.lineTo(c+0.5,e+0.5);this.ctx.closePath();this.ctx.stroke()}};openark_lchart.prototype.draw_line_path=function(e,a){if(e.length==0){return}if(e.length==1){this.draw_line(e[0].x-2,e[0].y,e[0].x+2,e[0].y,a*0.8);this.draw_line(e[0].x,e[0].y-2,e[0].x,e[0].y+2,a*0.8);return}if(this.isIE){var c=document.createElement("v:polyline");var b=new Array(e.length*2);for(i=0;i<e.length;++i){b[i*2]=e[i].x;b[i*2+1]=e[i].y}var d=b.join(",");c.setAttribute("points",d);c.setAttribute("stroked","true");c.setAttribute("filled","false");c.setAttribute("strokecolor",""+this.current_color);c.setAttribute("strokeweight",""+a+"pt");this.container.appendChild(c)}else{this.ctx.lineWidth=a;this.ctx.strokeWidth=0.5;this.ctx.beginPath();this.ctx.moveTo(e[0].x+0.5,e[0].y+0.5);for(i=1;i<e.length;++i){this.ctx.lineTo(e[i].x+0.5,e[i].y+0.5)}this.ctx.stroke()}};openark_lchart.prototype.draw_text=function(b){var a=document.createElement("div");a.style.position="absolute";a.style.left=""+b.left+"px";a.style.top=""+b.top+"px";a.style.width=""+b.width+"px";a.style.height=""+b.height+"px";a.style.textAlign=""+b.text_align;a.style.verticalAlign="top";if(b.font_size){a.style.fontSize=""+b.font_size+"pt"}if(b.background){a.style.background=""+b.background}a.innerHTML=b.text;this.container.appendChild(a)};openark_lchart.prototype.on_mouse_move=function(a){if(!a){var a=window.event}var h=a.clientX-(findPosX(this.container)-(window.pageXOffset||document.documentElement.scrollLeft||document.body.scrollLeft||0));var g=a.clientY-(findPosY(this.container)-(window.pageYOffset||document.documentElement.scrollTop||document.body.scrollTop||0));var c=h-this.chart_origin_x;var b=this.chart_origin_y-g;var e=((c<=this.chart_width)&&(b<=this.chart_height)&&(c>=0)&&(b>=-20));var l=Math.round((this.multi_series[0].length-1)*(c/this.chart_width));if((b<0)&&(b>=-20)&&(c>=this.chart_width-10)){l=this.multi_series[0].length-1}if(e){this.series_legend_values=new Array(this.multi_series.length);for(series=0;series<this.multi_series.length;++series){var j=this.multi_series[series][l];if(j==null){this.series_legend_values[series]="n/a"}else{this.series_legend_values[series]=j.toFixed(this.y_axis_round_digits+1)}}if(this.position_pointer==null){this.position_pointer=document.createElement("div");this.position_pointer.style.position="absolute";this.position_pointer.style.top=""+(this.chart_origin_y-this.chart_height)+"px";this.position_pointer.style.width="2px";this.position_pointer.style.filter="alpha(opacity=60)";this.position_pointer.style.opacity="0.6";this.position_pointer.style.height=""+(this.chart_height)+"px";this.position_pointer.style.backgroundColor=openark_lchart.position_pointer_color;this.canvas_shadow.appendChild(this.position_pointer)}if(this.tsstart){var k=new Date(this.tsstart);if(this.tsstep%(60*60*24)==0){k.setDate(this.tsstart.getDate()+(this.tsstep/(60*60*24))*l)}else{if(this.tsstep%(60*60)==0){k.setHours(this.tsstart.getHours()+(this.tsstep/(60*60))*l)}else{if(this.tsstep%(60)==0){k.setMinutes(this.tsstart.getMinutes()+(this.tsstep/(60))*l)}else{k.setSeconds(this.tsstart.getSeconds()+this.tsstep*l)}}}var d=(this.tsstep<60*60*24);this.timestamp_legend_value=format_date(k,d)}this.update_legend();var f=Math.floor(this.chart_origin_x+l*this.chart_width/(this.multi_series_dot_positions[0].length-1));this.position_pointer.style.visibility="visible";this.position_pointer.style.left=""+(f)+"px"}else{this.clear_position_pointer_and_legend_values(a)}};openark_lchart.prototype.on_mouse_out=function(a){if(!a){var a=window.event}if(a.relatedTarget==this.position_pointer){return}this.clear_position_pointer_and_legend_values(a)};openark_lchart.prototype.clear_position_pointer_and_legend_values=function(a){if(this.position_pointer!=null){this.position_pointer.style.visibility="hidden"}this.series_legend_values=null;this.update_legend()};openark_lchart.prototype.update_legend=function(){if(this.tsstart){if(this.series_legend_values==null){this.timestamp_value_container.innerHTML="[type]"}else{this.timestamp_value_container.innerHTML=this.timestamp_legend_value.replace(/ /g,"&nbsp;")}}for(i=0;i<this.series_labels.length;++i){if(this.series_legend_values==null){this.legend_values_containers[i].innerHTML=""}else{var a=0;if(this.y_axis_min<this.y_axis_max){a=100*((this.series_legend_values[i]-this.y_axis_min)/(this.y_axis_max-this.y_axis_min))}this.legend_values_containers[i].innerHTML=""+this.series_legend_values[i]}}};function findPosX(a){var b=0;if(a.offsetParent){while(1){b+=a.offsetLeft;if(!a.offsetParent){break}a=a.offsetParent}}else{if(a.x){b+=a.x}}return b}function findPosY(b){var a=0;if(b.offsetParent){while(1){a+=b.offsetTop;if(!b.offsetParent){break}b=b.offsetParent}}else{if(b.y){a+=b.y}}return a}function format_date(c,b){pad=function(f,e){var d=""+f;while(d.length<e){d="0"+d}return d};var a=""+c.getFullYear()+"-"+pad(c.getMonth()+1,2)+"-"+pad(c.getDate(),2);if(b){a+=" "+pad(c.getHours(),2)+":"+pad(c.getMinutes(),2)}return a};
    """
openark_schart = """
    openark_schart=function(a,b){if(a.style.width==""){this.canvas_width=b.width}else{this.canvas_width=a.style.width}if(a.style.height==""){this.canvas_height=b.height}else{this.canvas_height=a.style.height}this.title_height=0;this.chart_title="";this.x_axis_values_height=30;this.y_axis_values_width=35;this.x_axis_labels=[];this.x_axis_label_positions=[];this.y_axis_labels=[];this.y_axis_label_positions=[];this.dot_x_positions=[];this.dot_y_positions=[];this.dot_values=[];this.dot_colors=[];this.plot_colors=openark_schart.plot_colors;this.container=a;this.isIE=false;this.current_color=null;this.recalc();return this};openark_schart.title_font_size=10;openark_schart.title_color="#505050";openark_schart.axis_color="#707070";openark_schart.axis_font_size=8;openark_schart.plot_colors=["#9aed32","#ff8c00"];openark_schart.max_dot_size=9;openark_schart.prototype.recalc=function(){this.chart_width=this.canvas_width-this.y_axis_values_width-openark_schart.max_dot_size;this.chart_height=this.canvas_height-(this.x_axis_values_height+this.title_height)-openark_schart.max_dot_size;this.chart_origin_x=this.y_axis_values_width;this.chart_origin_y=this.canvas_height-this.x_axis_values_height};openark_schart.prototype.create_graphics=function(){this.container.innerHTML="";this.isIE=(/MSIE/.test(navigator.userAgent)&&!window.opera);this.container.style.position="relative";this.container.style.color=""+openark_schart.axis_color;this.container.style.fontSize=""+openark_schart.axis_font_size+"pt";this.container.style.fontFamily="Helvetica,Verdana,Arial,sans-serif";if(this.isIE){var b=document.createElement("div");b.style.width=this.canvas_width;b.style.height=this.canvas_height;this.container.appendChild(b)}else{var a=document.createElement("canvas");a.setAttribute("width",this.canvas_width);a.setAttribute("height",this.canvas_height);this.canvas=a;this.container.appendChild(this.canvas);this.ctx=this.canvas.getContext("2d")}};openark_schart.prototype.hex_to_rgb=function(b){if(b.substring(0,1)=="#"){b=b.substring(1)}var a=[];b.replace(/(..)/g,function(c){a.push(parseInt(c,16))});return a};openark_schart.prototype.toHex=function(a){if(a==0){return"00"}return"0123456789abcdef".charAt((a-a%16)/16)+"0123456789abcdef".charAt(a%16)};openark_schart.prototype.rgb_to_hex=function(c,b,a){return"#"+this.toHex(c)+this.toHex(b)+this.toHex(a)};openark_schart.prototype.gradient=function(c,b,a){var e=this.hex_to_rgb(c);var d=this.hex_to_rgb(b);return this.rgb_to_hex(Math.floor(e[0]+(d[0]-e[0])*a/100),Math.floor(e[1]+(d[1]-e[1])*a/100),Math.floor(e[2]+(d[2]-e[2])*a/100))};openark_schart.prototype.parse_url=function(a){a=a.replace(/[+]/gi," ");var b={};var c=a.indexOf("?");if(c>=0){a=a.substring(c+1)}tokens=a.split("&");for(i=0;i<tokens.length;++i){param_tokens=tokens[i].split("=");if(param_tokens.length==2){b[param_tokens[0]]=param_tokens[1]}}return b};openark_schart.prototype.read_google_url=function(b){params=this.parse_url(b);this.title_height=0;if(params.chtt){this.chart_title=params.chtt;this.title_height=20}if(params.chco){var h=params.chco.split(",");this.plot_colors=[];for(i=0;i<h.length;++i){this.plot_colors.push("#"+h[i])}}this.recalc();if(params.chxl){var d=params.chxl;var j=[];for(i=0,pos=0;pos>=0;++i){pos=d.indexOf(""+i+":|");if(pos<0){j.push(d);break}var c=d.substring(0,pos);if(c.length){if(c.substring(c.length-1)=="|"){c=c.substring(0,c.length-1)}j.push(c)}d=d.substring(pos+3)}this.x_axis_labels=j[0].split("|");this.x_axis_label_positions=[];for(i=0;i<this.x_axis_labels.length;++i){var g=Math.floor(this.chart_origin_x+i*this.chart_width/(this.x_axis_labels.length-1));this.x_axis_label_positions.push(g)}this.y_axis_labels=j[1].split("|");this.y_axis_label_positions=[];for(i=0;i<this.y_axis_labels.length;++i){var f=Math.floor(this.chart_origin_y-i*this.chart_height/(this.y_axis_labels.length-1));this.y_axis_label_positions.push(f)}}if(params.chd){var n=params.chd;var e=n.substring(0,2);if(e=="t:"){this.dot_x_positions=[];this.dot_y_positions=[];this.dot_values=[];this.dot_colors=[];n=n.substring(2);var h=n.split("|");var a=h[0].split(",");var k=h[1].split(",");var m=null;if(h.length>2){m=h[2].split(",")}else{m=new Array(a.length)}for(i=0;i<m.length;++i){var g=Math.floor(this.chart_origin_x+parseInt(a[i])*this.chart_width/100);this.dot_x_positions.push(g);var f=Math.floor(this.chart_origin_y-parseInt(k[i])*this.chart_height/100);this.dot_y_positions.push(f);var l=null;if(m[i]&&(m[i]!="_")){l=Math.floor(m[i]*openark_schart.max_dot_size/100)}this.dot_values.push(l);this.dot_colors.push(this.gradient(this.plot_colors[0],this.plot_colors[1],m[i]))}}}this.redraw()};openark_schart.prototype.redraw=function(){this.create_graphics();this.draw()};openark_schart.prototype.draw=function(){if(this.chart_title){this.draw_text({text:this.chart_title,left:0,top:0,width:this.canvas_width,height:this.title_height,text_align:"center",font_size:openark_schart.title_font_size})}for(i=0;i<this.dot_values.length;++i){if(this.dot_values[i]!=null){this.draw_circle(this.dot_x_positions[i],this.dot_y_positions[i],this.dot_values[i],this.dot_colors[i])}}this.set_color(openark_schart.axis_color);for(i=0;i<this.x_axis_label_positions.length;++i){if(this.x_axis_labels[i]){this.draw_text({text:""+this.x_axis_labels[i],left:this.x_axis_label_positions[i]-25,top:this.chart_origin_y+openark_schart.max_dot_size+5,width:50,height:openark_schart.axis_font_size,text_align:"center"})}}for(i=0;i<this.y_axis_label_positions.length;++i){if(this.y_axis_labels[i]){this.draw_text({text:""+this.y_axis_labels[i],left:0,top:this.y_axis_label_positions[i]-openark_schart.axis_font_size+Math.floor(openark_schart.axis_font_size/3),width:this.y_axis_values_width-openark_schart.max_dot_size-5,height:openark_schart.axis_font_size,text_align:"right"})}}};openark_schart.prototype.set_color=function(a){this.current_color=a;if(!this.isIE){this.ctx.strokeStyle=a}};openark_schart.prototype.draw_circle=function(b,e,a,c){if(this.isIE){var d=document.createElement("v:oval");d.style.position="absolute";d.style.left=b-a;d.style.top=e-a;d.style.width=a*2;d.style.height=a*2;d.setAttribute("stroked","false");d.setAttribute("filled","true");d.setAttribute("fillcolor",""+c);this.container.appendChild(d)}else{this.ctx.fillStyle=this.dot_colors[i];this.ctx.beginPath();this.ctx.arc(b,e,a,0,Math.PI*2,true);this.ctx.closePath();this.ctx.fill()}};openark_schart.prototype.draw_text=function(b){var a=document.createElement("div");a.style.position="absolute";a.style.left=""+b.left+"px";a.style.top=""+b.top+"px";a.style.width=""+b.width+"px";a.style.height=""+b.height+"px";a.style.textAlign=""+b.text_align;a.style.verticalAlign="top";if(b.font_size){a.style.fontSize=""+b.font_size+"pt"}a.innerHTML=b.text;this.container.appendChild(a)};
    """
corners_image = """data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAAXNSR0IArs4c6QAAAAlwSFlzAAALEwAACxMBAJqcGAAAAAd0SU1FB9oGGREdC6h6BI8AAAAZdEVYdENvbW1lbnQAQ3JlYXRlZCB3aXRoIEdJTVBXgQ4XAAAA2UlEQVQoz5WSS2rEMBBESx/apqWV7384n0CrlhCNPlloMgmZiePUphG8B4Uoc54nPsPMIQTvvbUWwBijtZZzLqU8Gb8OEcUYmdk5h28hom3b9n0XEVV9CER0HAcRGWPwEudcjJGIUkqqagGs91t6xRizKgDwzMzMF/TTYeZaqw0h/Oj9W5xzIQTrvcftrA+094X/0Q9njHGfHmPY1tp9obVmc8699zt07z3nbEsppZQ55zU951ykBbB2cuHMOVVVRABYAKqaUhKRt9167yKyhvS11uXUWv+c9wcqkoXk2CZntQAAAABJRU5ErkJggg%3D%3D"""

def get_monitored_host():
    monitored_host = options.monitored_host
    if not monitored_host:
        monitored_host = options.host
    return monitored_host


def is_local_monitoring():
    monitored_host = get_monitored_host()
    if monitored_host in ["localhost", "127.0.0.1"]:
        return True
    if monitored_host in [socket.getfqdn(), socket.gethostname()]:
        return True
    return False


def should_monitor_os():
    if options.force_os_monitoring:
        return True
    if is_local_monitoring():
        return True
    return False


def is_neglectable_variable(variable_name):
    if variable_name.startswith("ssl_"):
        return True
    if variable_name.startswith("ndb_"):
        return True
    if variable_name == "last_query_cost":
        return True
    if variable_name == "rpl_status":
        return True
    return False


def normalize_variable_value(variable_name, variable_value):
    # First, handle special cases.
    # I'm fearful about name colisions, where values do not agree.
    if variable_name == "concurrent_insert":
        if variable_value == "never":
            variable_value = 0
        elif variable_value == "auto":
            variable_value = 1
        elif variable_value == "always":
            variable_value = 2
        return
    if variable_value == "off":
        variable_value = 0
    elif variable_value == "on":
        variable_value = 1
    elif variable_value == "demand":
        variable_value = 2
    elif variable_value == "no":
        variable_value = 0
    elif variable_value == "yes":
        variable_value = 1
    elif variable_value == "not started":
        variable_value = 0
    elif variable_value == "started":
        variable_value = 1
    if variable_name == "delay_key_write":
        if variable_value == "all":
            variable_value = 2
    return variable_value


def get_global_variables():
    global_variables = [
        "auto_increment_increment",
        "binlog_cache_size",
        "bulk_insert_buffer_size",
        "concurrent_insert",
        "connect_timeout",
        "delay_key_write",
        "delayed_insert_limit",
        "delayed_insert_timeout",
        "delayed_queue_size",
        "expire_logs_days",
        "foreign_key_checks",
        "group_concat_max_len",
        "innodb_additional_mem_pool_size",
        "innodb_autoextend_increment",
        "innodb_autoinc_lock_mode",
        "innodb_buffer_pool_size",
        "innodb_checksums",
        "innodb_commit_concurrency",
        "innodb_concurrency_tickets",
        "innodb_fast_shutdown",
        "innodb_file_io_threads",
        "innodb_file_per_table",
        "innodb_flush_log_at_trx_commit",
        "innodb_force_recovery",
        "innodb_lock_wait_timeout",
        "innodb_log_buffer_size",
        "innodb_log_file_size",
        "innodb_log_files_in_group",
        "innodb_max_dirty_pages_pct",
        "innodb_max_purge_lag",
        "innodb_mirrored_log_groups",
        "innodb_open_files",
        "innodb_rollback_on_timeout",
        "innodb_stats_on_metadata",
        "innodb_support_xa",
        "innodb_sync_spin_loops",
        "innodb_table_locks",
        "innodb_thread_concurrency",
        "innodb_thread_sleep_delay",
        "join_buffer_size",
        "key_buffer_size",
        "key_cache_age_threshold",
        "key_cache_block_size",
        "key_cache_division_limit",
        "large_files_support",
        "large_page_size",
        "large_pages",
        "locked_in_memory",
        "log_queries_not_using_indexes",
        "log_slow_queries",
        "long_query_time",
        "low_priority_updates",
        "max_allowed_packet",
        "max_binlog_cache_size",
        "max_binlog_size",
        "max_connect_errors",
        "max_connections",
        "max_delayed_threads",
        "max_error_count",
        "max_heap_table_size",
        "max_insert_delayed_threads",
        "max_join_size",
        "max_length_for_sort_data",
        "max_prepared_stmt_count",
        "max_relay_log_size",
        "max_seeks_for_key",
        "max_sort_length",
        "max_sp_recursion_depth",
        "max_tmp_tables",
        "max_user_connections",
        "max_write_lock_count",
        "min_examined_row_limit",
        "multi_range_count",
        "myisam_data_pointer_size",
        "myisam_max_sort_file_size",
        "myisam_repair_threads",
        "myisam_sort_buffer_size",
        "myisam_use_mmap",
        "net_buffer_length",
        "net_read_timeout",
        "net_retry_count",
        "net_write_timeout",
        "old_passwords",
        "open_files_limit",
        "optimizer_prune_level",
        "optimizer_search_depth",
        "port",
        "preload_buffer_size",
        "profiling",
        "profiling_history_size",
        "protocol_version",
        "pseudo_thread_id",
        "query_alloc_block_size",
        "query_cache_limit",
        "query_cache_min_res_unit",
        "query_cache_size",
        "query_cache_type",
        "query_cache_wlock_invalidate",
        "query_prealloc_size",
        "range_alloc_block_size",
        "read_buffer_size",
        "read_only",
        "read_rnd_buffer_size",
        "relay_log_space_limit",
        "rpl_recovery_rank",
        "server_id",
        "skip_external_locking",
        "skip_networking",
        "skip_show_database",
        "subordinate_compressed_protocol",
        "subordinate_net_timeout",
        "subordinate_transaction_retries",
        "slow_launch_time",
        "slow_query_log",
        "sort_buffer_size",
        "sql_auto_is_null",
        "sql_big_selects",
        "sql_big_tables",
        "sql_buffer_result",
        "sql_log_bin",
        "sql_log_off",
        "sql_log_update",
        "sql_low_priority_updates",
        "sql_max_join_size",
        "sql_notes",
        "sql_quote_show_create",
        "sql_safe_updates",
        "sql_select_limit",
        "sql_warnings",
        "sync_binlog",
        "sync_frm",
        "table_cache",
        "table_definition_cache",
        "table_lock_wait_timeout",
        "table_open_cache",
        "thread_cache_size",
        "thread_stack",
        "timed_mutexes",
        "timestamp",
        "tmp_table_size",
        "transaction_alloc_block_size",
        "transaction_prealloc_size",
        "unique_checks",
        "updatable_views_with_limit",
        "wait_timeout",
        "warning_count",
        ]
    return global_variables


def get_extra_variables():
    extra_variables = [
        "hostname",
        "datadir",
        "tmpdir",
        "version",
        "sql_mode",
        ]
    return extra_variables


def get_mountpoint_usage_percent(path):
    """
    Find the mountpoint for the given path; return the integer number of disk used percent.
    """
    mountpoint = os.path.abspath(path)
    while not os.path.ismount(mountpoint):
        mountpoint = os.path.split(mountpoint)[0]

    statvfs = os.statvfs(mountpoint)
    #mount_usage = int(100-100.0*statvfs.f_bavail/statvfs.f_blocks)

    # The following calculation follows df.c (part of coreutils)
    # statvfs.f_blocks is total blocks
    # statvfs.f_bavail is available blocks
    # statvfs.f_bfree is blocks available to root

    used_blocks = statvfs.f_blocks - statvfs.f_bfree
    nonroot_total_blocks = used_blocks + statvfs.f_bavail

    used_percent = 100*used_blocks/nonroot_total_blocks
    if 100*used_blocks % nonroot_total_blocks != 0:
        used_percent = used_percent+1

    return used_percent


def get_page_io_activity():
    """
    From /proc/vmstat, read pages in/out, swap in/out (since kast reboot)
    """
    vmstat_file = open("/proc/vmstat")
    lines = vmstat_file.readlines()
    vmstat_file.close()
    
    vmstat_dict = {}
    for line in lines:
        tokens = line.split()
        vmstat_dict[tokens[0]] = tokens[1]
        
    pgpgin = None 
    pgpgout = None 
    pswpin = None 
    pswpout = None
    if vmstat_dict["pgpgin"]:
        pgpgin = int(vmstat_dict["pgpgin"])
    if vmstat_dict["pgpgout"]:
        pgpgout = int(vmstat_dict["pgpgout"]) 
    if vmstat_dict["pswpin"]:
        pswpin = int(vmstat_dict["pswpin"])
    if vmstat_dict["pswpout"]:
        pswpout = int(vmstat_dict["pswpout"]) 

    return (pgpgin, pgpgout, pswpin, pswpout)


def get_custom_query_ids():
    """
    Returns ids of custom queries
    """
    global custom_query_ids
    if custom_query_ids is None:
        query = """SELECT custom_query_id, chart_name FROM %s.custom_query_view""" % database_name 
        rows = get_rows(query, write_conn)
        custom_query_ids = [int(row["custom_query_id"]) for row in rows]
    return custom_query_ids


def get_custom_query_ids_charts_enabled():
    """
    Returns ids of custom queries which express presentable charts; also read matching chart names
    """
    global custom_query_ids_charts_enabled
    global custom_chart_names
    if custom_query_ids_charts_enabled is None:
        query = """SELECT custom_query_id, chart_name FROM %s.custom_query_view WHERE chart_enabled = 1""" % database_name 
        rows = get_rows(query, write_conn)
        custom_query_ids_charts_enabled = [int(row["custom_query_id"]) for row in rows]
        custom_chart_names = [row["chart_name"] for row in rows]
    return custom_query_ids_charts_enabled


def get_custom_chart_names():
    get_custom_query_ids_charts_enabled()
    return custom_chart_names


def get_custom_status_variables():
    custom_status_variables = ["custom_%d" % i for i in get_custom_query_ids()]
    return custom_status_variables


def get_custom_time_status_variables():
    custom_time_status_variables = ["custom_%d_time" % i for i in get_custom_query_ids()]
    return custom_time_status_variables


def get_custom_status_variables_psec():
    custom_status_variables_psec = ["custom_%d_psec" % i for i in get_custom_query_ids()]
    return custom_status_variables_psec


def get_additional_status_variables():
    additional_status_variables = [
        "queries",
        "open_table_definitions",
        "opened_table_definitions",
        "innodb_buffer_pool_pages_total",
        "innodb_buffer_pool_pages_free",
        "innodb_buffer_pool_pages_data",
        "innodb_buffer_pool_pages_dirty",
        "innodb_buffer_pool_pages_flushed",
        "innodb_buffer_pool_pages_misc",
        "innodb_buffer_pool_reads", 
        "innodb_buffer_pool_read_requests", 
        "innodb_buffer_pool_reads", 
        "innodb_buffer_pool_read_ahead",
        "innodb_buffer_pool_read_ahead_evicted",
        "innodb_os_log_written", 
        "innodb_row_lock_waits", 
        "innodb_row_lock_current_waits", 
        "innodb_row_lock_time", 
        "innodb_rows_read", 
        "innodb_rows_inserted", 
        "innodb_rows_updated", 
        "innodb_rows_deleted",
    ]
    additional_status_variables.extend(get_custom_status_variables())
    additional_status_variables.extend(get_custom_time_status_variables())
    
    return additional_status_variables


def fetch_status_variables():
    """
    Fill in the status_dict. We make point of filling in all variables, even those not existing,
    for having the dictionary hold the keys. Based on these keys, tables and views are created.
    So it is important that we have the dictionary include all possible keys.
    """
    if status_dict:
        return status_dict

    # Make sure some status variables exist: these are required due to 5.0 - 5.1
    # or minor versions incompatibilities.
    for additional_status_variable in get_additional_status_variables():
        status_dict[additional_status_variable] = None
    query = "SHOW GLOBAL STATUS"
    rows = get_rows(query);
    for row in rows:
        variable_name = row["Variable_name"].lower().strip()
        variable_value = row["Value"].lower()
        if not is_neglectable_variable(variable_name):
            status_dict[variable_name] = normalize_variable_value(variable_name, variable_value)

    # Listing of interesting global variables:
    global_variables = get_global_variables()
    extra_variables = get_extra_variables()
    for variable_name in global_variables:
        status_dict[variable_name.lower()] = None
    query = "SHOW GLOBAL VARIABLES"
    rows = get_rows(query);
    for row in rows:
        variable_name = row["Variable_name"].lower().strip()
        variable_value = row["Value"].lower()
        if variable_name in global_variables:
            status_dict[variable_name] = normalize_variable_value(variable_name, variable_value)
        elif variable_name in extra_variables:
            extra_dict[variable_name] = variable_value

    status_dict["metadata_revision"] = revision_number
    
    verbose("Global status & variables recorded")

    # Main & subordinate status
    status_dict["main_status_position"] = None
    status_dict["main_status_file_number"] = None
    subordinate_status_variables = [
        "Read_Main_Log_Pos",
        "Relay_Log_Pos",
        "Exec_Main_Log_Pos",
        "Relay_Log_Space",
        "Seconds_Behind_Main",
        ]
    for variable_name in subordinate_status_variables:
        status_dict[variable_name.lower()] = None
    if not options.skip_check_replication:
        try:
            query = "SHOW MASTER STATUS"
            main_status = get_row(query)
            if main_status:
                status_dict["main_status_position"] = main_status["Position"]
                log_file_name = main_status["File"]
                log_file_number = int(log_file_name.rsplit(".")[-1])
                status_dict["main_status_file_number"] = log_file_number
            query = "SHOW SLAVE STATUS"
            subordinate_status = get_row(query)
            if subordinate_status:
                for variable_name in subordinate_status_variables:
                    status_dict[variable_name.lower()] = subordinate_status[variable_name]
            verbose("Main and subordinate status recorded")
        except:
            # An exception can be thrown if the user does not have enough privileges:
            print_error("Cannot show main & subordinate status. Skipping")
            pass

    # OS (linux) load average
    status_dict["os_loadavg_millis"] = None
    # OS (linux) CPU
    status_dict["os_cpu_user"] = None
    status_dict["os_cpu_nice"] = None
    status_dict["os_cpu_system"] = None
    status_dict["os_cpu_idle"] = None
    status_dict["os_total_cpu_cores"] = None
    # OS Mem
    status_dict["os_mem_total_kb"] = None
    status_dict["os_mem_free_kb"] = None
    status_dict["os_mem_active_kb"] = None
    status_dict["os_swap_total_kb"] = None
    status_dict["os_swap_free_kb"] = None

    status_dict["os_root_mountpoint_usage_percent"] = None
    status_dict["os_datadir_mountpoint_usage_percent"] = None
    status_dict["os_tmpdir_mountpoint_usage_percent"] = None

    status_dict["os_page_ins"] = None
    status_dict["os_page_outs"] = None
    status_dict["os_swap_ins"] = None
    status_dict["os_swap_outs"] = None

    # We monitor OS params if this is the local machine, or --force-os-monitoring has been specified
    if should_monitor_os():
        try:
            f = open("/proc/stat")
            proc_stat_lines = f.readlines()
            f.close()
            first_line = proc_stat_lines[0]
            
            tokens = first_line.split()
            os_cpu_user, os_cpu_nice, os_cpu_system, os_cpu_idle = tokens[1:5]
            status_dict["os_cpu_user"] = int(os_cpu_user)
            status_dict["os_cpu_nice"] = int(os_cpu_nice)
            status_dict["os_cpu_system"] = int(os_cpu_system)
            status_dict["os_cpu_idle"] = int(os_cpu_idle)

            cpu_lines = [proc_stat_line for proc_stat_line in proc_stat_lines if re.match("^cpu[\\d]+[\\s]", proc_stat_line)]            
            status_dict["os_total_cpu_cores"] = len(cpu_lines)
            
            verbose("OS CPU info recorded")
        except:
            verbose("Cannot read /proc/stat. Skipping")

        try:
            f = open("/proc/loadavg")
            first_line = f.readline()
            f.close()

            tokens = first_line.split()
            loadavg_1_min = float(tokens[0])
            loadavg_millis = int(loadavg_1_min * 1000)
            status_dict["os_loadavg_millis"] = loadavg_millis
            verbose("OS load average info recorded")
        except:
            verbose("Cannot read /proc/loadavg. Skipping")

        try:
            f = open("/proc/meminfo")
            lines = f.readlines()
            f.close()

            for line in lines:
                tokens = line.split()
                param_name = tokens[0].replace(":", "").lower()
                param_value = int(tokens[1])
                if param_name == "memtotal":
                    status_dict["os_mem_total_kb"] = param_value
                elif param_name == "memfree":
                    status_dict["os_mem_free_kb"] = param_value
                elif param_name == "active":
                    status_dict["os_mem_active_kb"] = param_value
                elif param_name == "swaptotal":
                    status_dict["os_swap_total_kb"] = param_value
                elif param_name == "swapfree":
                    status_dict["os_swap_free_kb"] = param_value
            verbose("OS mem info recorded")
        except:
            verbose("Cannot read /proc/meminfo. Skipping")

        # Filesystems:
        try:
            status_dict["os_root_mountpoint_usage_percent"] = get_mountpoint_usage_percent("/")
            status_dict["os_datadir_mountpoint_usage_percent"] = get_mountpoint_usage_percent(extra_dict["datadir"])
            status_dict["os_tmpdir_mountpoint_usage_percent"] = get_mountpoint_usage_percent(extra_dict["tmpdir"])
            verbose("OS mountpoints info recorded")
        except:
            verbose("Cannot read mountpoints info. Skipping")
            
        try:
            (pgpgin, pgpgout, pswpin, pswpout) = get_page_io_activity()

            status_dict["os_page_ins"] = pgpgin
            status_dict["os_page_outs"] = pgpgout
            status_dict["os_swap_ins"] = pswpin
            status_dict["os_swap_outs"] = pswpout
            
            verbose("OS page io activity recorded")
        except:
            verbose("Cannot read page io activity. Skipping")

    else:
        verbose("Non-local monitoring; will not read OS data")

    return status_dict


def get_status_variables_columns():
    """
    Return all columns participating in the status variables table. Most of these are STATUS variables.
    Others are parameters. Others yet represent subordinate or main status etc.
    """
    status_dict = fetch_status_variables()
    return sorted_list(status_dict.keys())


def get_variables_and_status_columns():
    variables_columns = get_global_variables()
    status_columns = [column_name for column_name in get_status_variables_columns() if not column_name in variables_columns]
    return variables_columns, status_columns

def get_known_signed_diff_status_variables():
    known_signed_diff_status_variables = [
        "threads_cached",
        "threads_connected",
        "threads_running",
        "open_table_definitions",
        "open_tables",
        "subordinate_open_temp_tables",
        "qcache_free_blocks",
        "qcache_free_memory",
        "qcache_queries_in_cache",
        "qcache_total_blocks",
        "innodb_page_size",
        "innodb_buffer_pool_pages_total",
        "innodb_buffer_pool_pages_free",
        "innodb_buffer_pool_pages_data",
        "innodb_buffer_pool_pages_dirty",
        "innodb_buffer_pool_pages_flushed",
        "innodb_buffer_pool_pages_misc",
        "key_blocks_unused",
        "key_cache_block_size",
        "main_status_position",
        "read_main_log_pos",
        "relay_log_pos",
        "exec_main_log_pos",
        "relay_log_space",
        "seconds_behind_main",
        ]
    return known_signed_diff_status_variables


def is_signed_column(column_name):
    return column_name in get_known_signed_diff_status_variables()


def get_column_sign_indicator(column_name):
    if is_signed_column(column_name):
        return "SIGNED"
    else:
        return "UNSIGNED"


def create_status_variables_table():
    columns_listing = ",\n".join(["%s BIGINT %s" % (column_name, get_column_sign_indicator(column_name)) for column_name in get_status_variables_columns()])
    query = """CREATE TABLE %s.%s (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            %s,
            UNIQUE KEY ts (ts)
       )
        """ % (database_name, table_name, columns_listing)

    table_created = False
    try:
        act_query(query)
        table_created = True
    except MySQLdb.Error:
        pass

    if table_created:
        verbose("%s table created" % table_name)
    else:
        verbose("%s table exists" % table_name)
    return table_created



def create_metadata_table():
    query = """
            DROP TABLE IF EXISTS %s.metadata
        """ % database_name
    try:
        act_query(query)
    except MySQLdb.Error:
        exit_with_error("Cannot execute %s" % query )

    query = """
        CREATE TABLE %s.metadata (
            revision SMALLINT UNSIGNED NOT NULL,
            build BIGINT UNSIGNED NOT NULL,
            last_deploy TIMESTAMP NOT NULL,
            last_deploy_successful TINYINT UNSIGNED NOT NULL DEFAULT 0,
            mysql_version VARCHAR(255) CHARSET ascii NOT NULL,
            database_name VARCHAR(255) CHARSET utf8 NOT NULL,
            custom_queries VARCHAR(4096) CHARSET ascii NOT NULL
        )
        """ % database_name

    try:
        act_query(query)
        verbose("metadata table created")
    except MySQLdb.Error:
        exit_with_error("Cannot create table %s.metadata" % database_name)

    query = """
        REPLACE INTO %s.metadata
            (revision, build, last_deploy_successful, mysql_version, database_name, custom_queries)
        VALUES
            (%d, %d, 0, '%s', '%s', '')
        """ % (database_name, revision_number, build_number, get_monitored_host_mysql_version(), database_name)
    act_query(query)


def finalize_deploy():
    query = """UPDATE ${database_name}.metadata 
        SET last_deploy_successful = 1
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)


def create_numbers_table():
    query = """
            DROP TABLE IF EXISTS %s.numbers
        """ % database_name
    try:
        act_query(query)
    except MySQLdb.Error:
        exit_with_error("Cannot execute %s" % query )

    query = """
        CREATE TABLE %s.numbers (
            n SMALLINT UNSIGNED NOT NULL,
            PRIMARY KEY (n)
        )
        """ % database_name

    try:
        act_query(query)
        verbose("numbers table created")
    except MySQLdb.Error:
        exit_with_error("Cannot create table %s.numbers" % database_name)

    numbers_values = ",".join(["(%d)" % n for n in range(0,4096)])
    query = """
        INSERT IGNORE INTO %s.numbers
        VALUES %s
        """ % (database_name, numbers_values)
    act_query(query)


def create_charts_api_table():
    query = """
            DROP TABLE IF EXISTS %s.charts_api
        """ % database_name
    try:
        act_query(query)
    except MySQLdb.Error:
        exit_with_error("Cannot execute %s" % query )

    query = """
        CREATE TABLE %s.charts_api (
            chart_width SMALLINT UNSIGNED NOT NULL,
            chart_height SMALLINT UNSIGNED NOT NULL,
            simple_encoding CHAR(62) CHARSET ascii COLLATE ascii_bin,
            service_url VARCHAR(128) CHARSET ascii COLLATE ascii_bin
        )
        """ % database_name

    try:
        act_query(query)
        verbose("charts_api table created")
    except MySQLdb.Error:
        exit_with_error("Cannot create table %s.charts_api" % database_name)

    query = """
        INSERT INTO %s.charts_api
            (chart_width, chart_height, simple_encoding, service_url)
        VALUES
            (%d, %d, 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789', '%s')
        """ % (database_name, options.chart_width, options.chart_height, options.chart_service_url.replace("'", "''"))
    act_query(query)


def create_html_components_table():
    query = """
            DROP TABLE IF EXISTS %s.html_components
        """ % database_name
    try:
        act_query(query)
    except MySQLdb.Error:
        exit_with_error("Cannot execute %s" % query )

    query = """
        CREATE TABLE %s.html_components (
            openark_lchart TEXT CHARSET ascii COLLATE ascii_bin,
            openark_schart TEXT CHARSET ascii COLLATE ascii_bin,
            common_css TEXT CHARSET ascii COLLATE ascii_bin
        )
        """ % database_name

    common_css = """
            div.http_html_embed {
                background: #f6f0f0;
                margin: 10px 10px 0px 10px;
                padding: 4px 0px 4px 0px;
            }
            body {
                background:#e0e0e0 none repeat scroll 0%;
                color:#505050;
                font-family:Verdana,Arial,Helvetica,sans-serif;
                font-size:9pt;
                line-height:1.5;
            }
            .corner { position: absolute; width: 8px; height: 8px; background: url('data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAIAAACQkWg2AAAAAXNSR0IArs4c6QAAAAlwSFlzAAALEwAACxMBAJqcGAAAAAd0SU1FB9oGGREdC6h6BI8AAAAZdEVYdENvbW1lbnQAQ3JlYXRlZCB3aXRoIEdJTVBXgQ4XAAAA2UlEQVQoz5WSS2rEMBBESx/apqWV7384n0CrlhCNPlloMgmZiePUphG8B4Uoc54nPsPMIQTvvbUWwBijtZZzLqU8Gb8OEcUYmdk5h28hom3b9n0XEVV9CER0HAcRGWPwEudcjJGIUkqqagGs91t6xRizKgDwzMzMF/TTYeZaqw0h/Oj9W5xzIQTrvcftrA+094X/0Q9njHGfHmPY1tp9obVmc8699zt07z3nbEsppZQ55zU951ykBbB2cuHMOVVVRABYAKqaUhKRt9167yKyhvS11uXUWv+c9wcqkoXk2CZntQAAAABJRU5ErkJggg%3D%3D') no-repeat; font-size: 0; }
            .tl { top: 0; left: 0; background-position: 0 0; }
            .tr { top: 0; right: 0; background-position: -8px 0; }
            .bl { bottom: 0; left: 0; background-position: 0 -8px; }
            .br { bottom: 0; right: 0; background-position: -8px -8px; }
            .clear {
                clear: both;
            }
            .nobr {
                white-space: nowrap;
            }
            strong {
                font-weight: bold;
            }
            strong.db {
                font-weight: bold;
                font-size: 24px;
                color:#f26522;
            }
            a {
                color:#f26522;
                text-decoration:none;
            }
            hr {
                border: 0;
                height: 1px;
                background: #e0e0e0;
            }
            h1 {
                margin: 0 0 10 0;
                font-size: 16px;
            }
            h2 {
                font-size:13.5pt;
                font-weight:normal;
            }
            h2 a {
                font-weight:normal;
                font-size: 60%;
            }
            h3 {
                font-size:10.5pt;
                font-weight:normal;
            }
            h3 a {
                font-weight:normal;
                font-size: 80%;
            }
            div.header_content {
                padding: 10px;
            }
            div.custom_chart {
                margin-bottom: 40px;
            }
        """
    
    try:
        act_query(query)
        verbose("html_components table created")
    except MySQLdb.Error:
        exit_with_error("Cannot create table %s.html_components" % database_name)

    query = """
        INSERT INTO %s.html_components
            (openark_lchart, openark_schart, common_css)
        VALUES
            ('${openark_lchart}', '${openark_schart}', '${common_css}')
        """ % database_name
    query = query.replace("${openark_lchart}", openark_lchart.replace("'","''"))
    query = query.replace("${openark_schart}", openark_schart.replace("'","''"))
    query = query.replace("${common_css}", common_css.replace("'","''"))

    act_query(query)


def create_custom_query_table():
    query = """
        CREATE TABLE IF NOT EXISTS %s.custom_query (
          custom_query_id INT UNSIGNED,
          enabled BOOL NOT NULL DEFAULT 1,
          query_eval VARCHAR(4095) CHARSET utf8 COLLATE utf8_bin NOT NULL,
          description VARCHAR(255) CHARSET utf8 COLLATE utf8_bin DEFAULT NULL,
          chart_type ENUM('value', 'value_psec', 'time') NOT NULL DEFAULT 'value',
          chart_order TINYINT(4) NOT NULL DEFAULT '0',
          PRIMARY KEY (custom_query_id)
        )
        """ % database_name
    # Upgrade:
    alter_query = """
        ALTER TABLE %s.custom_query 
          MODIFY COLUMN chart_type ENUM('value', 'value_psec', 'time', 'none') NOT NULL DEFAULT 'value'
        """ % database_name

    try:
        act_query(query)
        act_query(alter_query)
        verbose("custom_query table created")
    except MySQLdb.Error:
        if options.debug:
            traceback.print_exc()
        exit_with_error("Cannot create table %s.custom_query" % database_name)
    
    query = """UPDATE ${database_name}.metadata 
        SET custom_queries = 
            (SELECT 
                IFNULL(
                  GROUP_CONCAT(
                    CONCAT(custom_query_id, ':', chart_type) 
                    ORDER BY chart_order, custom_query_id SEPARATOR ','
                  )
                  , '') 
            FROM ${database_name}.custom_query
            ) 
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)


def create_custom_query_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.custom_query_view AS
          SELECT
            custom_query_id,
            enabled,
            query_eval,
            description,
            chart_type,
            chart_order,
            CASE chart_type
                WHEN 'value' THEN CONCAT('custom_', custom_query_id)
                WHEN 'value_psec' THEN CONCAT('custom_', custom_query_id, '_psec')
                WHEN 'time' THEN CONCAT('custom_', custom_query_id, '_time')
                WHEN 'none' THEN NULL
            END AS chart_name,
            CASE chart_type
                WHEN 'none' THEN 0
                ELSE 1
            END AS chart_enabled
          FROM
            ${database_name}.custom_query
          ORDER BY 
            custom_query.chart_order, custom_query.custom_query_id
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("custom_query_view created")



def create_custom_query_top_navigation_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.custom_query_top_navigation_view AS
          SELECT
            GROUP_CONCAT(
                CONCAT('<a href="#custom_', custom_query_view.custom_query_id, '_chart">', custom_query_view.description, '</a>') 
                ORDER BY 
                    custom_query_view.chart_order, custom_query_view.custom_query_id
                SEPARATOR ' | '
            ) AS custom_query_top_navigation
          FROM
            ${database_name}.custom_query_view
          WHERE
            ${database_name}.custom_query_view.chart_enabled = 1
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("custom_query_top_navigation_view created")



def execute_custom_query(custom_query_id, query_eval):
    start_time = time.time()
    rows = get_rows(query_eval)
    end_time = time.time()
    
    query_error_message = "Custom query is expected to produce a single (int) column, single row result. custom_query_id=%d" % custom_query_id
    if len(rows) != 1:
        return print_error(query_error_message)
        
    row = rows[0]
    if len(row) != 1:
        return print_error(query_error_message)
    
    # Expect an integer value:
    custom_value = None
    try:
        raw_custom_value = row.values()[0]
        if raw_custom_value is None:
            custom_value = None
        else:
            custom_value = int(raw_custom_value)
    except ValueError:
        return print_error(query_error_message)
    
    # We measure time in milliseconds
    query_time = int(1000*(end_time - start_time))
    return custom_value, query_time


def collect_custom_data():
    if options.skip_custom:
        verbose("Skipping custom queries")
        return

    verbose("Collecting custom data")
    
    query = """
            SELECT 
              * 
            FROM 
              ${database_name}.custom_query
            WHERE
              enabled = 1
        """
    query = query.replace("${database_name}", database_name)
    custom_updates = []
    for custom_query in get_rows(query, write_conn):
        custom_query_id = int(custom_query["custom_query_id"])
        query_eval = custom_query["query_eval"]
        description = custom_query["description"]
        verbose("Custom query: %s" % description)
        custom_query_result = execute_custom_query(custom_query_id, query_eval)
        if custom_query_result is not None:
            custom_value, query_time = custom_query_result
            if custom_value is None:
                custom_updates.append("custom_%d = NULL, custom_%d_time = %d" % (custom_query_id, custom_query_id, query_time,))
            else:
                custom_updates.append("custom_%d = %d, custom_%d_time = %d" % (custom_query_id, custom_value, custom_query_id, query_time,))
    if custom_updates:
        query = """
            UPDATE 
              %s.%s 
            SET %s
            WHERE 
              id = %d""" % (
            database_name, table_name, 
            ",".join(custom_updates), 
            status_variables_insert_id)
        act_query(query) 


def get_processlist_summary():
    query = "SHOW PROCESSLIST"
    num_sleeping_processes = 0
    printed_rows = []
    # Get processes in descending time order:
    sorted_rows = sorted(get_rows(query), key=lambda row: int(row["Time"]), reverse=True)
    for row in sorted_rows:
        command = row["Command"]
        if command == "Sleep":
            num_sleeping_processes = num_sleeping_processes+1
        else:
            for column_name in row.keys():
                if row[column_name] is None:
                    row[column_name] = "NULL"
            printed_row = """
     Id: %s
   User: %s
   Host: %s
     db: %s
Command: %s
   Time: %s
  State: %s
   Info: %s
-------""" % (
                row["Id"], row["User"], row["Host"], row["db"], row["Command"], row["Time"], row["State"], row["Info"], 
            )
            printed_rows.append(printed_row)
    printed_rows.append("Sleeping: %d processes" % num_sleeping_processes)
    return "\n".join(printed_rows)            
    
    
def create_alert_condition_table():
    query = """
        CREATE TABLE IF NOT EXISTS %s.alert_condition (
          alert_condition_id INT UNSIGNED AUTO_INCREMENT,
          enabled BOOL NOT NULL DEFAULT 1,
          condition_eval VARCHAR(4095) CHARSET utf8 COLLATE utf8_bin NOT NULL,
          description VARCHAR(255) CHARSET utf8 COLLATE utf8_bin DEFAULT NULL,
          error_level ENUM('debug', 'info', 'warning', 'error', 'critical') NOT NULL DEFAULT 'error',
          alert_delay_minutes SMALLINT UNSIGNED NOT NULL DEFAULT 0,
          repetitive_alert BOOL NOT NULL DEFAULT 0,
          PRIMARY KEY (alert_condition_id)
        )
        """ % database_name

    # Upgrade:
    alter_query_0 = """
        ALTER TABLE %s.alert_condition 
          DROP COLUMN pre_condition_eval;
        """ % database_name
    alter_query_1 = """
        ALTER TABLE %s.alert_condition 
          ADD COLUMN monitored_host_condition_eval VARCHAR(4095) CHARSET utf8 COLLATE utf8_bin NOT NULL
          AFTER condition_eval
        """ % database_name

    try:
        act_query(query)
        act_query_ignore_error(alter_query_0)
        act_query_ignore_error(alter_query_1)
        verbose("alert_condition table created")
    except MySQLdb.Error:
        if options.debug:
            traceback.print_exc()
        exit_with_error("Cannot create table %s.alert_condition" % database_name)


def create_alert_table():
    query = """
        CREATE TABLE IF NOT EXISTS %s.alert (
          `alert_id` INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
          `alert_condition_id` INT(11) UNSIGNED NOT NULL,
          `sv_report_sample_id` INT(11) DEFAULT NULL,
          PRIMARY KEY (`alert_id`),
          UNIQUE KEY `alert_condition_sv_report_sample` (`sv_report_sample_id`, `alert_condition_id`),
          KEY `alert_condition_id` (`alert_condition_id`)
        )
        """ % database_name

    try:
        act_query(query)
        verbose("alert table created")
    except MySQLdb.Error:
        if options.debug:
            traceback.print_exc()
        exit_with_error("Cannot create table %s.alert" % database_name)


def create_alert_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.alert_view AS
          SELECT
            alert_condition.alert_condition_id,
            sv_report_sample.id AS sv_report_sample_id,
            TRIM(alert_condition.condition_eval) AS condition_eval,
            TRIM(alert_condition.monitored_host_condition_eval) AS monitored_host_condition_eval,
            TRIM(alert_condition.description) AS description,
            alert_condition.error_level AS error_level,
            sv_report_sample.ts AS ts
          FROM
            ${database_name}.alert
            JOIN ${database_name}.alert_condition ON (alert_condition.alert_condition_id = alert.alert_condition_id)
            JOIN ${database_name}.sv_report_sample ON (alert.sv_report_sample_id = sv_report_sample.id)
          ORDER BY 
            alert.sv_report_sample_id, alert.alert_condition_id
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("alert_view created")


def create_alert_pending_table():
    query = """
        CREATE TABLE IF NOT EXISTS %s.alert_pending (
          alert_pending_id INT(11) UNSIGNED NOT NULL AUTO_INCREMENT,
          alert_condition_id INT(11) UNSIGNED NOT NULL,
          sv_report_sample_id_start INT(11) DEFAULT NULL,
          sv_report_sample_id_end INT(11) DEFAULT NULL,
          ts_notified DATETIME DEFAULT NULL,
          resolved BOOL NOT NULL DEFAULT 0,
          PRIMARY KEY (`alert_pending_id`),
          UNIQUE KEY (`alert_condition_id`)
        )
        """ % database_name

    try:
        act_query(query)
        verbose("alert_pending table created")
    except MySQLdb.Error:
        if options.debug:
            traceback.print_exc()
        exit_with_error("Cannot create table %s.alert_pending" % database_name)


def create_alert_pending_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.alert_pending_view AS
          SELECT
            alert_pending.alert_pending_id AS alert_pending_id,
            alert_condition.alert_condition_id AS alert_condition_id,
            TRIM(alert_condition.condition_eval) AS condition_eval,
            TRIM(alert_condition.monitored_host_condition_eval) AS monitored_host_condition_eval,
            TRIM(alert_condition.description) AS description,
            alert_condition.error_level AS error_level,
            alert_condition.alert_delay_minutes AS alert_delay_minutes,
            sv_report_sample_start.ts AS ts_start,
            sv_report_sample_end.ts AS ts_end,
            (TIMESTAMPDIFF(SECOND, sv_report_sample_start.ts, sv_report_sample_end.ts)+3) DIV 60 AS elapsed_minutes, 
            (TIMESTAMPDIFF(SECOND, sv_report_sample_start.ts, sv_report_sample_end.ts)+3) DIV 60 >= alert_delay_minutes AS in_error,
            alert_pending.ts_notified IS NOT NULL AS is_notified,
            alert_pending.ts_notified AS ts_notified,
            alert_pending.resolved AS resolved,
            alert_condition.repetitive_alert AS repetitive_alert 
          FROM
            ${database_name}.alert_pending
            JOIN ${database_name}.alert_condition ON (alert_pending.alert_condition_id = alert_condition.alert_condition_id)
            JOIN ${database_name}.sv_report_sample AS sv_report_sample_start ON (alert_pending.sv_report_sample_id_start = sv_report_sample_start.id)
            JOIN ${database_name}.sv_report_sample AS sv_report_sample_end ON (alert_pending.sv_report_sample_id_end = sv_report_sample_end.id)
          ORDER BY
            resolved ASC,
            in_error DESC,
            error_level DESC,
            elapsed_minutes DESC,
            alert_condition_id ASC
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("alert_pending_view created")


def create_alert_pending_html_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.alert_pending_html_view AS
          SELECT
            CONCAT('
                <html>
                    <head>
                    <title>', metadata.database_name, ' monitoring: pending alerts</title>
                    <meta http-equiv="refresh" content="600" />
                    <style type="text/css">
                        ', common_css, '
                        div.header {
                            position: relative;
                            float: left;
                            background: #ffffff;
                            margin-bottom: 10px;
                        }
                        div.table_container {
                            padding: 10px;
                            background: #ffffff;
                            position: relative;
                            float: left;
                        }
                        table {
                            border-collapse: collapse;
                            font-size: 9pt;
                        }
                        table, tr, td {
                            border: 2px solid #e0e0e0;
                        }
                        tr.header {
                            font-weight: bold;
                        }
                        td {
                            padding: 3px 6px 3px 6px;
                        }
                        .el_ok {
                            color: #000000;
                            background-color: #00ff00;
                        }
                        .el_awaiting {
                            color: #ffffff;
                            background-color: #c0c0c0;
                        }
                        .el_debug {
                            color: #000000;
                            background-color: #ffffff;
                        }
                        .el_info {
                            color: #ffffff;
                            background-color: #0000ff;
                        }
                        .el_warning {
                            color: #000000;
                            background-color: #ffff00;
                        }
                        .el_error {
                            color: #ffffff;
                            background-color: #ff0000;
                        }
                        .el_critical {
                            color: #ffffff;
                            background-color: #000000;
                        }
                    </style>
                    </head>
                    <body>
                        <a name=""></a>
                        <div class="table_container">
                            <div class="header"></div>
                            <div class="clear"></div>
                            <table class="table">
                                <tr>
                                    <td colspan="6">
                                        <h1><strong class="db">', metadata.database_name, '</strong> database monitoring: pending alerts report</h1>
                                        Report generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on <strong>',
                                            DATE_FORMAT(NOW(),'%%b %%D %%Y, %%H:%%i'), '</strong>. Revision: <strong>', metadata.revision, '</strong>, build: <strong>', metadata.build, '</strong>. MySQL version: <strong>', metadata.mysql_version, '</strong>
                                        <br/><br/><br/>    
                                    </td>
                                </tr>
                                ',
                                IF(GROUP_CONCAT(alert_pending_id) IS NULL, 
                                  '<tr class="row"><td class="el_ok">OK</td><td colspan="5">No pending alerts</td></tr>',
                                  CONCAT(
                                    '<tr class="row header">
                                      <td>Error level</td> 
                                      <td>Description</td> 
                                      <td>Alert start time</td> 
                                      <td>Elapsed minutes</td> 
                                      <td>Notification time</td>
                                      <td>Repeating notification</td>
                                    </tr>',
                                      GROUP_CONCAT(
                                          '<tr class="row">',
                                            '<td class="el_', IF(ts_notified IS NULL, 'awaiting', error_level), '">', IF(ts_notified IS NULL, 'awaiting: ', ''), error_level, '</td>', 
                                            '<td>', description, '</td>', 
                                            '<td>', ts_start, '</td>', 
                                            '<td>', elapsed_minutes, '</td>', 
                                            '<td', IF(ts_notified IS NULL, ' class="el_awaiting"', ''), '>', IFNULL(ts_notified, CONCAT('ETA: ', ts_start + INTERVAL alert_delay_minutes MINUTE)), '</td>', 
                                            '<td>', IF(repetitive_alert, 'Yes', '-'), '</td>', 
                                          '</tr>'
                                        SEPARATOR '')
                                    )
                                  ),
                                '
                            </table>
                        </div>
                        <div class="clear"></div>
                        ',
                        IF(GROUP_CONCAT(alert_pending_id) IS NULL, 
                          '
                          <br/>
                          <div>
                            There are no pending alerts
                          </div>', 
                          '') ,'
                    </body>
                </html>
                %s
            ') AS html
          FROM
            ${database_name}.html_components,
            ${database_name}.metadata LEFT JOIN ${database_name}.alert_pending_view ON (NULL IS NULL)
          WHERE
            (resolved = 0) OR (resolved IS NULL)
    """ % ""
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("alert_pending_html_view created")


def create_alert_email_message_items_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.alert_email_message_items_view AS
          SELECT
            alert_pending_id,
            IF(
              resolved,
              CONCAT(
                'Resolved: ', description, '
    alert_condition id: ', alert_condition_id, ' [pending id: ', alert_pending_id, ']'
              ),
              CONCAT(
                UPPER(error_level), ': ', description, '
    This ', error_level, ' alert is pending for ', elapsed_minutes, ' minutes, since ', ts_start, '
    alert_condition id: ', alert_condition_id, ' [pending id: ', alert_pending_id, ']'
              )
            ) AS message_item
          FROM
            ${database_name}.alert_pending_view
          WHERE
            in_error > 0
            AND ((is_notified = 0) OR (repetitive_alert != 0) OR (resolved = 1))
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("alert_email_message_items_view created")


def create_alert_condition_query_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.alert_condition_query_view AS
          SELECT
            CONCAT(
              'SELECT ',
              GROUP_CONCAT(
                CONCAT(condition_eval, ' AS condition_', alert_condition_id) 
                SEPARATOR ' ,'),
              ' FROM ${database_name}.sv_report_sample
              ORDER BY id DESC 
              LIMIT 1;'
            ) AS query
          FROM
            ${database_name}.alert_condition
          WHERE
            enabled = 1
        """
    query = query.replace("${database_name}", database_name)

    try:
        act_query(query)
        verbose("alert_condition query view created")
    except MySQLdb.Error:
        exit_with_error("Cannot create view %s.alert_condition_query_view" % database_name)


def generate_alert_condition_query():

    query = """
            SELECT 
              alert_condition_id, 
              IF(monitored_host_condition_eval = '', true, monitored_host_condition_eval) AS monitored_host_condition_eval, 
              IF(condition_eval = '', true, condition_eval) AS condition_eval 
            FROM 
              ${database_name}.alert_condition
            WHERE
              enabled = 1
        """
    query = query.replace("${database_name}", database_name)
    rows = get_rows(query, write_conn)
    if not rows:
        return (None, None, None)
    
    alert_condition_ids = [int(row["alert_condition_id"]) for row in rows]

    query_conditions = ["%s AS condition_%d" % (row["condition_eval"], int(row["alert_condition_id"])) for row in rows]
    query = """
        SELECT
          id, 
          %s 
        FROM
          ${database_name}.sv_report_sample
        ORDER BY 
          id DESC
        LIMIT 1
      """ % (",".join(query_conditions))
    query = query.replace("${database_name}", database_name)

    monitored_host_query_conditions = ["%s AS condition_%d" % (row["monitored_host_condition_eval"], int(row["alert_condition_id"])) for row in rows]
    monitored_host_query = """
        SELECT
          %s 
      """ % (",".join(monitored_host_query_conditions))
    
    return alert_condition_ids, query, monitored_host_query


def write_alert(alert_condition_id, report_sample_id):
    query = """
        INSERT /*! IGNORE */ INTO 
          ${database_name}.alert (alert_condition_id, sv_report_sample_id) 
        VALUES 
          (%d, %d)
        """ % (alert_condition_id, report_sample_id)
    query = query.replace("${database_name}", database_name)
    act_query(query)



def write_alert_pending(alert_condition_id, report_sample_id):
    query = """
        INSERT INTO 
          ${database_name}.alert_pending (alert_condition_id, sv_report_sample_id_start, sv_report_sample_id_end) 
        VALUES 
          (%d, %d, %d)
        ON DUPLICATE KEY UPDATE
          sv_report_sample_id_end = %d
        """ % (alert_condition_id, report_sample_id, report_sample_id, report_sample_id)
    query = query.replace("${database_name}", database_name)
    act_query(query)
    
    
def mark_resolved_alerts(report_sample_id):
    query = """
        UPDATE 
            ${database_name}.alert_pending
        SET
          resolved = 1
        WHERE
          sv_report_sample_id_end < %d
        """ % report_sample_id
    query = query.replace("${database_name}", database_name)
    num_affected_rows = act_query(query)
    verbose("Marked %d pending alerts as resolved" % num_affected_rows)
    
    
def remove_resolved_alerts():
    query = """
        DELETE FROM 
            ${database_name}.alert_pending
        WHERE
          resolved = 1
        """
    query = query.replace("${database_name}", database_name)
    num_affected_rows = act_query(query)
    verbose("Deleted %d resolved pending alerts" % num_affected_rows)


def mark_notified_pending_alerts(notified_pending_alert_ids):    
    if not notified_pending_alert_ids:
        return

    query = """
        UPDATE 
          ${database_name}.alert_pending
        SET 
          ts_notified = NOW()
        WHERE 
          alert_pending_id IN (%s)
        """ % ",".join(["%d" % notified_pending_alert_id for notified_pending_alert_id in notified_pending_alert_ids])
    query = query.replace("${database_name}", database_name)
    act_query(query)


def check_alerts():
    if options.skip_alerts:
        verbose("Skipping alerts")
        return

    alert_condition_ids, query, monitored_host_query = generate_alert_condition_query()
    if not alert_condition_ids:
        verbose("No alert conditions defined")
        return
    
    row = get_row(query, write_conn)
    monitored_host_row = get_row(monitored_host_query, monitored_conn)
    report_sample_id = int(row["id"])
    num_alerts = 0
    
    for alert_condition_id in alert_condition_ids:
        condition_result = row["condition_%d" % alert_condition_id]
        monitored_host_condition_result = monitored_host_row["condition_%d" % alert_condition_id]
        if condition_result is None:
            condition_result = 0
        if monitored_host_condition_result is None:
            monitored_host_condition_result = 0
        if int(condition_result) != 0 and int(monitored_host_condition_result) != 0: 
            write_alert(alert_condition_id, report_sample_id)
            write_alert_pending(alert_condition_id, report_sample_id)
            num_alerts += 1
    verbose("Found %s alerts" % num_alerts)
    mark_resolved_alerts(report_sample_id)
    
    notified_pending_alert_ids = send_alert_email()
    if notified_pending_alert_ids:
        # Alerts which have been notified must be marked as such
        mark_notified_pending_alerts(notified_pending_alert_ids)
    remove_resolved_alerts()


def send_alert_email():
    """
    Send an email including all never-sent pending alerts.
    Returns the ids of pending alerts
    """    
    query = """
      SELECT 
        alert_email_message_items_view.message_item, 
        alert_email_message_items_view.alert_pending_id, 
        alert_pending.resolved
      FROM 
        ${database_name}.alert_email_message_items_view
        JOIN alert_pending USING (alert_pending_id)
        """
    query = query.replace("${database_name}", database_name)
    
    rows = get_rows(query, write_conn)
    if options.skip_emails and rows:
        verbose("--skip-emails requested. Not sending alert mail, although there are %d unnotified alerts" % len(rows))
        return None

    if not rows:
        # No problems / resolved problems to report
        if not options.force_emails:
            return None
        # Force an OK email    
        email_message = """
Database OK: %s

This is an alert mail sent by mycheckpoint, monitoring your %s MySQL database.
All seems to be well.
                """ % (database_name, database_name,)
        email_subject = "%s: mycheckpoint OK notification" % database_name
        send_email_message("alert notifications", email_subject, email_message)
        return None
        

    message_items = [(row["message_item"], int(row["resolved"])) for row in rows]
    alert_pending_ids = [row["alert_pending_id"] for row in rows]
    
    num_resolved_items = 0
    num_non_resolved_items = 0
    email_rows = []
    for (message_item, resolved) in message_items:
        if resolved:
            if num_resolved_items == 0:
                email_rows.append("-------")
            num_resolved_items = num_resolved_items+1
        else:
            num_non_resolved_items = num_non_resolved_items+1
        email_rows.append(message_item)
  
    processlist_clause = ""
    if num_non_resolved_items > 0:
        try:
            processlist_summary = get_processlist_summary()
            processlist_clause = """
-------
PROCESSLIST summary:
%s
                """ % (processlist_summary)
        except:
            print_error("Unable to get PROCESSLIST. Check for GRANTs")
    
    email_message = """
Database alert: %s, generated on %s

This is an alert mail sent by mycheckpoint, monitoring your %s MySQL database.
The following problems have been found:

%s

%s
        """ % (database_name, get_current_timestamp(), database_name, "\n\n".join(email_rows), processlist_clause)
    email_subject = "%s: mycheckpoint alert notification" % database_name
    if send_email_message("alert notifications", email_subject, email_message):
        return alert_pending_ids
    else:
        return None


def get_monitored_host_mysql_version():
    version = get_row("SELECT VERSION() AS version")["version"]
    return version

def is_same_deploy():
    try:
        query = """SELECT COUNT(*) AS same_deploy 
            FROM ${database_name}.metadata 
            WHERE 
              revision = %d 
              AND build = %d 
              AND mysql_version = '%s'
              AND database_name = '%s'
              AND custom_queries = 
                (
                  SELECT 
                    IFNULL(
                      GROUP_CONCAT(
                        CONCAT(custom_query_id, ':', chart_type) 
                        ORDER BY chart_order, custom_query_id SEPARATOR ','
                      )
                      , '') 
                  FROM 
                    ${database_name}.custom_query
                )
              AND last_deploy_successful = 1
              """ % (revision_number, build_number, get_monitored_host_mysql_version(), database_name)
        query = query.replace("${database_name}", database_name)
        same_deploy = get_row(query, write_conn)["same_deploy"]
        return (same_deploy > 0)
    except:
        return False


def column_name_relates_to_custom_query(column_name):
    if re.match("^custom_[\\d]+$", column_name):
        return True
    if re.match("^custom_[\\d]+_time$", column_name):
        return True
    return False


def get_custom_query_id_by_column_name(column_name):
    match = re.match("^custom_([\\d]+)(_.+)?$", column_name)
    if match is None:
        return None
    result = match.group(1)
    if result is None:
        return None
    return int(result)

    
def upgrade_status_variables_table():

    # I currently prefer SHOW COLUMNS over using INFORMATION_SCHEMA because of the time it takes
    # to access the INFORMATION_SCHEMA.COLUMNS table.
    query = """
            SHOW COLUMNS FROM %s.%s
        """ % (database_name, table_name)
    rows = get_rows(query, write_conn)
    existing_columns = [row["Field"] for row in rows]
    existing_column_types = dict([(row["Field"], row["Type"]) for row in rows])

    new_columns = [column_name for column_name in get_status_variables_columns() if column_name not in existing_columns]
    redundant_custom_columns = [column_name for column_name in existing_columns  if (column_name not in get_status_variables_columns() and column_name_relates_to_custom_query(column_name))]
    mismatch_signed_type_columns = [column_name for column_name in existing_column_types if (column_name in get_known_signed_diff_status_variables() and "unsigned" in existing_column_types[column_name])]
    alter_statements = []
    
    if new_columns:
        verbose("Will add the following columns to %s: %s" % (table_name, ", ".join(new_columns)))
        alter_statements.extend(["ADD COLUMN %s BIGINT %s" % (column_name, get_column_sign_indicator(column_name)) for column_name in new_columns])
    if redundant_custom_columns:
        verbose("Will remove the following columns from %s: %s" % (table_name, ", ".join(redundant_custom_columns)))
        alter_statements.extend(["DROP COLUMN %s" % column_name for column_name in redundant_custom_columns])
    if mismatch_signed_type_columns:
        verbose("Will modify the following columns in %s to SIGNED: %s" % (table_name, ", ".join(mismatch_signed_type_columns)))
        alter_statements.extend(["MODIFY COLUMN %s BIGINT SIGNED" % column_name for column_name in mismatch_signed_type_columns])
    if alter_statements:
        query = """ALTER TABLE %s.%s
                %s
        """ % (database_name, table_name, ",\n".join(alter_statements))
        act_query(query)
        verbose("status_variables table upgraded")
    return len(alter_statements)

    
def upgrade_status_variables_aggregation_table(aggregation_table_name):
    # We should have the exact same set of columns as in sv_sample
    query = """
            SHOW COLUMNS FROM %s.sv_sample
        """ % (database_name,)
    sv_sample_columns = [row["Field"] for row in get_rows(query, write_conn)]

    query = """
            SHOW COLUMNS FROM %s.%s
        """ % (database_name, aggregation_table_name)
    existing_columns = [row["Field"] for row in get_rows(query, write_conn)]

    new_columns = [column_name for column_name in sv_sample_columns if column_name not in existing_columns]
    alter_statements = []
    
    if new_columns:
        diff_columns = [column_name for column_name in new_columns if column_name.endswith("_diff")]
        psec_columns = [column_name for column_name in new_columns if column_name.endswith("_psec")]
        normal_columns = [column_name for column_name in new_columns if (column_name not in diff_columns and column_name not in psec_columns)]
        alter_statements.extend(["ADD COLUMN %s BIGINT %s" % (column_name, get_column_sign_indicator(column_name)) for column_name in normal_columns])
        alter_statements.extend(["ADD COLUMN %s BIGINT " % (column_name,) for column_name in diff_columns])
        # We do not add _psec columns, because of InnoDB's hard coded limitation of max 1000 columns per table.
        # The _psec columns are easily computed later on.
        if alter_statements:
            verbose("Will add the following columns to %s: %s" % (aggregation_table_name, ", ".join(normal_columns + diff_columns)))
    # TODO: remove unused columns
    # ...
    if alter_statements:
        query = """ALTER TABLE %s.%s
                %s
        """ % (database_name, aggregation_table_name, ",\n".join(alter_statements))
        act_query(query)
        verbose("%s table upgraded" % aggregation_table_name)
    return len(alter_statements)

    
def upgrade_status_variables_hour_aggregation_table():
    return upgrade_status_variables_aggregation_table("status_variables_aggregated_hour")


def upgrade_status_variables_day_aggregation_table():
    return upgrade_status_variables_aggregation_table("status_variables_aggregated_day")


def create_status_variables_latest_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_latest AS
          SELECT
            MAX(id) AS id_latest,
            MAX(ts) AS ts_latest
          FROM
            ${database_name}.${status_variables_table_name}
    """
    query = query.replace("${database_name}", database_name)
    query = query.replace("${status_variables_table_name}", table_name)
    act_query(query)

    verbose("sv_latest view created")


def create_status_variables_diff_view():
    global_variables, status_columns = get_variables_and_status_columns()
    # Global variables are used as-is
    global_variables_columns_listing = ",\n".join([" ${status_variables_table_alias}2.%s AS %s" % (column_name, column_name,) for column_name in global_variables])
    # status variables as they were:
    status_columns_listing = ",\n".join([" ${status_variables_table_alias}2.%s AS %s" % (column_name, column_name,) for column_name in status_columns])
    # Status variables are diffed. This does not make sense for all of them, but we do it for all nonetheless.
    diff_signed_columns_listing = ",\n".join([" ${status_variables_table_alias}2.%s - ${status_variables_table_alias}1.%s AS %s_diff" % (column_name, column_name, column_name, ) for column_name in status_columns if is_signed_column(column_name)])
    # When either sv1's or sv2's variable is NULL, the IF condition fails and we do the "-" math, leading again to NULL. 
    # I *want* the diff to be NULL. This makes more sense than choosing sv2's value.
    diff_unsigned_columns_listing = ",\n".join([" IF(${status_variables_table_alias}2.%s < ${status_variables_table_alias}1.%s, ${status_variables_table_alias}2.%s, ${status_variables_table_alias}2.%s - ${status_variables_table_alias}1.%s) AS %s_diff" % (column_name, column_name, column_name, column_name, column_name, column_name, ) for column_name in status_columns if not is_signed_column(column_name)])

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = MERGE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_diff AS
          SELECT
            ${status_variables_table_name}2.id,
            ${status_variables_table_name}2.ts,
            TIMESTAMPDIFF(SECOND, ${status_variables_table_name}1.ts, ${status_variables_table_name}2.ts) AS ts_diff_seconds,
            %s,
            %s,
            %s,
            %s
          FROM
            ${database_name}.${status_variables_table_name} AS ${status_variables_table_alias}2
            INNER JOIN ${database_name}.${status_variables_table_name} AS ${status_variables_table_alias}1
            ON (${status_variables_table_alias}1.id = ${status_variables_table_alias}2.id-GREATEST(1, IFNULL(${status_variables_table_alias}2.auto_increment_increment, 1)))
    """ % (status_columns_listing, diff_signed_columns_listing, diff_unsigned_columns_listing, global_variables_columns_listing)
    query = query.replace("${database_name}", database_name)
    query = query.replace("${status_variables_table_name}", table_name)
    query = query.replace("${status_variables_table_alias}", table_name)
    act_query(query)

    verbose("sv_diff view created")


def create_status_variables_sample_view():
    global_variables, status_columns = get_variables_and_status_columns()

    global_variables_columns_listing = ",\n".join(["%s" % (column_name,) for column_name in global_variables])
    status_columns_listing = ",\n".join([" %s" % (column_name,) for column_name in status_columns])
    diff_columns_listing = ",\n".join([" %s_diff" % (column_name,) for column_name in status_columns])
    change_psec_columns_listing = ",\n".join([" ROUND(%s_diff/ts_diff_seconds, 2) AS %s_psec" % (column_name, column_name,) for column_name in status_columns])

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = MERGE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_sample AS
          SELECT
            id,
            ts,
            ts_diff_seconds,
            %s,
            %s,
            %s,
            %s
          FROM
            ${database_name}.sv_diff
        """ % (status_columns_listing, diff_columns_listing, change_psec_columns_listing, global_variables_columns_listing)
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_sample view created")


def create_status_variables_hour_view():
    global_variables, status_columns = get_variables_and_status_columns()

    if options.skip_aggregation:
        # Rely on sv_sample
        global_variables_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in global_variables])
        status_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in status_columns])
        sum_diff_columns_listing = ",\n".join([" SUM(%s_diff) AS %s_diff" % (column_name, column_name,) for column_name in status_columns])
        avg_psec_columns_listing = ",\n".join([" ROUND(AVG(%s_psec), 2) AS %s_psec" % (column_name, column_name,) for column_name in status_columns])
        query = """
            CREATE
            OR REPLACE
            ALGORITHM = TEMPTABLE
            DEFINER = CURRENT_USER
            SQL SECURITY INVOKER
            VIEW ${database_name}.sv_hour AS
              SELECT
                MIN(id) AS id,
                DATE(ts) + INTERVAL HOUR(ts) HOUR AS ts,
                DATE(ts) + INTERVAL (HOUR(ts) + 1) HOUR AS end_ts,
                SUM(ts_diff_seconds) AS ts_diff_seconds,
                %s,
                %s,
                %s,
                %s
              FROM
                ${database_name}.sv_sample
              GROUP BY DATE(ts), HOUR(ts)
        """ % (status_columns_listing, sum_diff_columns_listing, avg_psec_columns_listing, global_variables_columns_listing)
    else:
        # Rely on aggregation table
        psec_columns_listing = ",\n".join([" ROUND(%s_diff/ts_diff_seconds, 2) AS %s_psec" % (column_name, column_name,) for column_name in status_columns])
        query = """
            CREATE
            OR REPLACE
            ALGORITHM = MERGE
            DEFINER = CURRENT_USER
            SQL SECURITY INVOKER
            VIEW ${database_name}.sv_hour AS
              SELECT
                *,
                %s
              FROM
                ${database_name}.status_variables_aggregated_hour
        """ % (psec_columns_listing,)
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_hour view created")


def create_status_variables_day_view():
    global_variables, status_columns = get_variables_and_status_columns()

    if options.skip_aggregation:
        # Rely on sv_sample    
        global_variables_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in global_variables])
        status_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in status_columns])
        sum_diff_columns_listing = ",\n".join([" SUM(%s_diff) AS %s_diff" % (column_name, column_name,) for column_name in status_columns])
        avg_psec_columns_listing = ",\n".join([" ROUND(AVG(%s_psec), 2) AS %s_psec" % (column_name, column_name,) for column_name in status_columns])
        query = """
            CREATE
            OR REPLACE
            ALGORITHM = TEMPTABLE
            DEFINER = CURRENT_USER
            SQL SECURITY INVOKER
            VIEW ${database_name}.sv_day AS
              SELECT
                MIN(id) AS id,
                DATE(ts) AS ts,
                DATE(ts) + INTERVAL 1 DAY AS end_ts,
                SUM(ts_diff_seconds) AS ts_diff_seconds,
                %s,
                %s,
                %s,
                %s
              FROM
                ${database_name}.sv_sample
              GROUP BY DATE(ts)
        """ % (status_columns_listing, sum_diff_columns_listing, avg_psec_columns_listing, global_variables_columns_listing)
    else:
        # Rely on aggregation table
        psec_columns_listing = ",\n".join([" ROUND(%s_diff/ts_diff_seconds, 2) AS %s_psec" % (column_name, column_name,) for column_name in status_columns])
        query = """
            CREATE
            OR REPLACE
            ALGORITHM = MERGE
            DEFINER = CURRENT_USER
            SQL SECURITY INVOKER
            VIEW ${database_name}.sv_day AS
              SELECT
                *,
                %s
              FROM
                ${database_name}.status_variables_aggregated_day
        """ % (psec_columns_listing,)
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_day view created")



def create_status_variables_hour_aggregation_table():
    if options.skip_aggregation:
        return

    aggregation_table_name = "status_variables_aggregated_hour";
    
    if options.rebuild_aggregation:
        query = """
                DROP TABLE IF EXISTS %s.%s
            """ % (database_name, aggregation_table_name)
        try:
            act_query(query)
        except MySQLdb.Error:
            exit_with_error("Cannot execute %s" % query )
        
    
    _global_variables, status_columns = get_variables_and_status_columns()

    global_variables_columns_listing = ",\n".join(["%s BIGINT %s" % (column_name, get_column_sign_indicator(column_name)) for column_name in get_status_variables_columns()])
    sum_diff_columns_listing = ",\n".join(["%s_diff BIGINT" % (column_name,) for column_name in status_columns])
    
    query = """CREATE TABLE %s.%s (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            end_ts TIMESTAMP DEFAULT '1980-01-01 00:00:00',
            ts_diff_seconds INT UNSIGNED,         
            %s,
            %s,
            UNIQUE KEY ts (ts)
       )
        """ % (database_name, aggregation_table_name, global_variables_columns_listing, sum_diff_columns_listing,)
    
    query = query.replace("${database_name}", database_name)
    
    table_created = False
    try:
        act_query(query)
        table_created = True
    except MySQLdb.Error, _err:
        if options.debug:
            traceback.print_exc()
        pass
    
    if table_created:
        verbose("%s table created" % aggregation_table_name)
    else:
        verbose("%s table exists" % aggregation_table_name)
    return table_created


def create_status_variables_day_aggregation_table():
    if options.skip_aggregation:
        return
    
    aggregation_table_name = "status_variables_aggregated_day";
    if options.rebuild_aggregation:
        query = """
                DROP TABLE IF EXISTS %s.%s
            """ % (database_name, aggregation_table_name)
        try:
            act_query(query)
        except MySQLdb.Error:
            exit_with_error("Cannot execute %s" % query )
        
    
    _global_variables, status_columns = get_variables_and_status_columns()

    global_variables_columns_listing = ",\n".join(["%s BIGINT %s" % (column_name, get_column_sign_indicator(column_name)) for column_name in get_status_variables_columns()])
    sum_diff_columns_listing = ",\n".join(["%s_diff BIGINT" % (column_name,) for column_name in status_columns])
    
    query = """CREATE TABLE %s.%s (
            id INT AUTO_INCREMENT PRIMARY KEY,
            ts DATE,
            end_ts DATE,
            ts_diff_seconds INT UNSIGNED,         
            %s,
            %s,
            UNIQUE KEY ts (ts)
       )
        """ % (database_name, aggregation_table_name, global_variables_columns_listing, sum_diff_columns_listing,)
    
    query = query.replace("${database_name}", database_name)

    table_created = False
    try:
        act_query(query)
        table_created = True
    except MySQLdb.Error:
        pass

    if table_created:
        verbose("%s table created" % aggregation_table_name)
    else:
        verbose("%s table exists" % aggregation_table_name)
    return table_created


def create_report_human_views():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = MERGE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_human_${view_name_extension} AS
          SELECT
            id,
            ts,
            CONCAT(
'Report period: ', TIMESTAMP(ts), ' to ', TIMESTAMP(ts) + INTERVAL ROUND(ts_diff_seconds/60) MINUTE, '. Period is ', ROUND(ts_diff_seconds/60), ' minutes (', round(ts_diff_seconds/60/60, 2), ' hours)
Uptime: ', uptime_percent,
    '% (Up: ', FLOOR(uptime/(60*60*24)), ' days, ', SEC_TO_TIME(uptime % (60*60*24)), ' hours)

OS:
    Load average: ', IFNULL(os_loadavg, 'N/A'), '
    CPU utilization: ', IFNULL(os_cpu_utilization_percent, 'N/A'), '%
    Memory: ', IFNULL(os_mem_used_mb, 'N/A'), 'MB used out of ', IFNULL(os_mem_total_mb, 'N/A'), 'MB (Active: ', IFNULL(os_mem_active_mb, 'N/A'), 'MB)
    Swap: ', IFNULL(os_swap_used_mb, 'N/A'), 'MB used out of ', IFNULL(os_swap_total_mb, 'N/A'), 'MB
    Mountpoints usage: root ', os_root_mountpoint_usage_percent, '%, datadir ', os_datadir_mountpoint_usage_percent, '%, tmpdir ', os_tmpdir_mountpoint_usage_percent, '%

InnoDB:
    innodb_buffer_pool_size: ', innodb_buffer_pool_size, ' bytes (', ROUND(innodb_buffer_pool_size/(1024*1024), 1), 'MB). Used: ',
        IFNULL(innodb_buffer_pool_used_percent, 'N/A'), '%
    Read hit: ', IFNULL(innodb_read_hit_percent, 'N/A'), '%
    Disk I/O: ', innodb_buffer_pool_reads_psec, ' reads/sec  ', innodb_buffer_pool_pages_flushed_psec, ' flushes/sec
    Estimated log written per hour: ', IFNULL(innodb_estimated_log_mb_written_per_hour, 'N/A'), 'MB
    Locks: ', innodb_row_lock_waits_psec, '/sec  current: ', innodb_row_lock_current_waits, '

MyISAM key cache:
    key_buffer_size: ', key_buffer_size, ' bytes (', ROUND(key_buffer_size/1024/1024, 1), 'MB). Used: ', IFNULL(key_buffer_used_percent, 'N/A'), '%
    Read hit: ', IFNULL(key_read_hit_percent, 'N/A'), '%  Write hit: ', IFNULL(key_write_hit_percent, 'N/A'), '%

DML:
    SELECT:  ', com_select_psec, '/sec  ', IFNULL(com_select_percent, 'N/A'), '%
    INSERT:  ', com_insert_psec, '/sec  ', IFNULL(com_insert_percent, 'N/A'), '%
    UPDATE:  ', com_update_psec, '/sec  ', IFNULL(com_update_percent, 'N/A'), '%
    DELETE:  ', com_delete_psec, '/sec  ', IFNULL(com_delete_percent, 'N/A'), '%
    REPLACE: ', com_replace_psec, '/sec  ', IFNULL(com_replace_percent, 'N/A'), '%
    SET:     ', com_set_option_psec, '/sec  ', IFNULL(com_set_option_percent, 'N/A'), '%
    COMMIT:  ', com_commit_psec, '/sec  ', IFNULL(com_commit_percent, 'N/A'), '%
    slow:    ', slow_queries_psec, '/sec  ', IFNULL(slow_queries_percent, 'N/A'), '% (slow time: ',
        long_query_time ,'sec)

Selects:
    Full scan: ', select_scan_psec, '/sec  ', IFNULL(select_scan_percent, 'N/A'), '%
    Full join: ', select_full_join_psec, '/sec  ', IFNULL(select_full_join_percent, 'N/A'), '%
    Range:     ', select_range_psec, '/sec  ', IFNULL(select_range_percent, 'N/A'), '%
    Sort merge passes: ', sort_merge_passes_psec, '/sec

Locks:
    Table locks waited:  ', table_locks_waited_psec, '/sec  ', IFNULL(table_lock_waited_percent, 'N/A'), '%

Tables:
    Table cache: ', table_cache_size, '. Used: ',
        IFNULL(table_cache_use_percent, 'N/A'), '%
    Opened tables: ', opened_tables_psec, '/sec

Temp tables:
    Max tmp table size:  ', tmp_table_size, ' bytes (', ROUND(tmp_table_size/(1024*1024), 1), 'MB)
    Max heap table size: ', max_heap_table_size, ' bytes (', ROUND(max_heap_table_size/(1024*1024), 1), 'MB)
    Created:             ', created_tmp_tables_psec, '/sec
    Created disk tables: ', created_tmp_disk_tables_psec, '/sec  ', IFNULL(created_disk_tmp_tables_percent, 'N/A'), '%

Connections:
    Max connections: ', max_connections, '. Max used: ', max_used_connections, '  ',
        IFNULL(max_connections_used_percent, 'N/A'), '%
    Connections: ', connections_psec, '/sec
    Aborted:     ', aborted_connects_psec, '/sec  ', IFNULL(aborted_connections_percent, 'N/A'), '%

Threads:
    Thread cache: ', thread_cache_size, '. Used: ', IFNULL(thread_cache_used_percent, 'N/A'), '%
    Created: ', threads_created_psec, '/sec

Replication:
    Main status file number: ', IFNULL(main_status_file_number, 'N/A'), ', position: ', IFNULL(main_status_position, 'N/A'), '
    Relay log space limit: ', IFNULL(relay_log_space_limit, 'N/A'), ', used: ', IFNULL(relay_log_space, 'N/A'), '  (',
        IFNULL(relay_log_space_used_percent, 'N/A'), '%)
    Seconds behind main: ', IFNULL(seconds_behind_main, 'N/A'), '
    Estimated time for subordinate to catch up: ', IFNULL(IF(seconds_behind_main_psec >= 0, NULL, FLOOR(-seconds_behind_main/seconds_behind_main_psec)), 'N/A'), ' seconds (',
        IFNULL(FLOOR(IF(seconds_behind_main_psec >= 0, NULL, -seconds_behind_main/seconds_behind_main_psec)/(60*60*24)), 'N/A'), ' days, ',
        IFNULL(SEC_TO_TIME(IF(seconds_behind_main_psec >= 0, NULL, -seconds_behind_main/seconds_behind_main_psec) % (60*60*24)), 'N/A'), ' hours)  ETA: ',
        IFNULL(TIMESTAMP(ts) + INTERVAL estimated_subordinate_catchup_seconds SECOND, 'N/A'), '
') AS report
          FROM
            ${database_name}.sv_report_${view_name_extension}
    """
    query = query.replace("${database_name}", database_name)

    for view_name_extension in ["sample", "hour", "day"]:
        custom_query = query.replace("${view_name_extension}", view_name_extension)
        act_query(custom_query)

    verbose("report human views created")


def create_report_24_7_view():
    """
    Generate a 24/7 report view
    """

    all_columns = report_columns
    columns_listing = ",\n".join(["AVG(%s) AS %s" % (column_name, column_name,) for column_name in all_columns])

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_24_7 AS
          SELECT
            NULL AS ts,
            WEEKDAY(ts) AS wd,
            HOUR(ts) AS hr,
            %s
          FROM
            ${database_name}.sv_report_sample
          GROUP BY WEEKDAY(ts), HOUR(ts)
          ORDER BY WEEKDAY(ts), HOUR(ts)
        """ % (columns_listing)
    query = query.replace("${database_name}", database_name)

    act_query(query)

    verbose("24/7 report view created")



def generate_google_chart_24_7_query(chart_column):
    # Gradient color:
    chart_color = "9aed32,ff8c00"

    query = """
          REPLACE(
          CONCAT(
            charts_api.service_url, '?cht=s&chs=', charts_api.chart_width, 'x', charts_api.chart_height,
            '&chts=303030,12&chtt=${chart_column}&chd=t:',
            CONCAT_WS('|',
              GROUP_CONCAT(ROUND(hr*100/23)),
              GROUP_CONCAT(ROUND(wd*100/6)),
              GROUP_CONCAT(ROUND(
                100*(${chart_column} - LEAST(0, ${chart_column}_min))/(${chart_column}_max - LEAST(0, ${chart_column}_min))
                ))
            ),
            '&chxt=x,y&chxl=0:|00|01|02|03|04|05|06|07|08|09|10|11|12|13|14|15|16|17|18|19|20|21|22|23|1:|Mon|Tue|Wed|Thu|Fri|Sat|Sun',
            '&chm=o&chco=${chart_color}'
          ), ' ', '+') AS ${chart_column}
        """
    query = query.replace("${chart_column}", chart_column)
    query = query.replace("${chart_color}", chart_color)

    return query


def create_report_google_chart_24_7_view(charts_list):
    charts_queries = [generate_google_chart_24_7_query(chart_column) for chart_column in charts_list]
    charts_query = ",".join(charts_queries)
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_chart_24_7 AS
          SELECT
            %s
          FROM
            ${database_name}.sv_report_24_7, ${database_name}.sv_report_24_7_minmax, ${database_name}.charts_api
        """ % charts_query
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("report 24/7 chart view created")


def create_report_html_24_7_view(report_columns):
    chart_queries = []
    js_queries = []
    for report_column in report_columns:
        query = """
            '<div class="chart_container">
                <div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>
                <h3>%s ', IFNULL(CONCAT('<a href="', %s, '">[url]</a>'), 'N/A'), '</h3>
                <div id="chart_div_%s" class="chart"></div>
            </div>',
            """ % (report_column.replace("_", " "), report_column, report_column)
        chart_queries.append(query)

        js_query = """
                IFNULL(
                    CONCAT('
                        new openark_schart(document.getElementById("chart_div_${report_column}"), {width: ', chart_width, ', height: ',  chart_height, '}).read_google_url("', ${report_column}, '");'
                    ),
                    '')
                """ 
        js_query = js_query.replace("${report_column}", report_column)
        js_queries.append(js_query)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_html_24_7 AS
          SELECT CONCAT('
            <html>
                <head>
                    <title>', metadata.database_name, ' monitoring: 24/7 report</title>
                    <!--[if IE]>
                        <xml:namespace ns="urn:schemas-microsoft-com:vml" prefix="v" />
                        <style> v\\\\:* { behavior: url(#default#VML); }</style >
                    <![endif]-->
                    <style type="text/css">
                        ', common_css, '
                        div.header {
                            position: relative;
                            float: left;
                            background: #ffffff;
                            margin-bottom: 10px;
                        }
                        div.chart {
                            white-space: nowrap;
                            width:', charts_api.chart_width, ';
                        }
                        div.chart_container {
                            position: relative;
                            float: left;
                            white-space: nowrap;
                            padding: 10px;
                            background: #ffffff;
                            width: ', charts_api.chart_width, ';
                            margin-right: 10px;
                            margin-bottom: 10px;
                        }
                    </style>
                    <script type="text/javascript" charset="utf-8">
                        ', openark_schart, '
                    </script>
                    <script type="text/javascript" charset="utf-8">
                        window.onload = function () {
                    ', %s, '
                        };
                    </script>
                </head>
                <body>
                    <a name=""></a>
                    <div class="header">
                        <div class="corner bl"></div><div class="corner br"></div>
                        <div class="header_content">
                            <h1><strong class="db">', metadata.database_name, '</strong> database monitoring: 24/7 report</h1>
                            Report generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on <strong>',
                                DATE_FORMAT(NOW(),'%%b %%D %%Y, %%H:%%i'), '</strong>. Revision: <strong>', metadata.revision, '</strong>, build: <strong>', metadata.build, '</strong>. MySQL version: <strong>', metadata.mysql_version, '</strong>    
                            <br/>The charts on this report are generated locally and do not send data over the net. Click the <a name="none">[url]</a> links to view Google image charts.
                        </div>
                    </div>
                    <div class="clear"></div>
                    ',
                    %s '
                </body>
            </html>
          ') AS html
          FROM
            ${database_name}.sv_report_chart_24_7, 
            ${database_name}.metadata, 
            ${database_name}.charts_api,
            ${database_name}.html_components
        """ % (",".join(js_queries), "".join(chart_queries))
    query = query.replace("${database_name}", database_name)
    query = query.replace("${global_width}", str(options.chart_width*3 + 30))
    query = query.replace("${corners_image}", corners_image.replace("'","''"))

    act_query(query)

    verbose("sv_report_html_24_7 created")


def create_report_recent_views():
    """
    Generate per-sample, per-hour and per-day 'recent' views, which only list the latest rows from respective full views.
    """
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = MERGE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_${view_name_extension}_recent AS
          SELECT *
          FROM
            ${database_name}.sv_report_${view_name_extension}, ${database_name}.sv_latest
          WHERE
            ts >= ${recent_timestamp}
        """
    query = query.replace("${database_name}", database_name)

    # In favour of charts, we round minutes in 10-min groups (e.g. 12:00, 12:10, 12:20, ...), and we therefroe
    # may include data slightly more than 24 hours ago.
    # With hour/day reports there's no such problem since nothing is to be rounded.
    recent_timestamp_map = {
        "sample": "ts_latest - INTERVAL SECOND(ts_latest) SECOND - INTERVAL (MINUTE(ts_latest) MOD 10) MINUTE - INTERVAL 24 HOUR",
        "hour": "ts_latest - INTERVAL 10 DAY",
        "day": "ts_latest - INTERVAL 1 YEAR",
        }
    for view_name_extension in recent_timestamp_map:
        custom_query = query
        custom_query = custom_query.replace("${view_name_extension}", view_name_extension)
        custom_query = custom_query.replace("${recent_timestamp}", recent_timestamp_map[view_name_extension])
        act_query(custom_query)

    verbose("recent reports views created")


def create_report_sample_recent_aggregated_view():
    all_columns = report_columns
    columns_listing = ",\n".join(["AVG(%s) AS %s" % (column_name, column_name,) for column_name in all_columns])
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_sample_recent_aggregated AS
          SELECT
            MAX(id) AS id,
            ts
              - INTERVAL SECOND(ts) SECOND
              - INTERVAL (MINUTE(ts) %% 10) MINUTE
              AS ts,
            %s
          FROM
            ${database_name}.sv_report_sample_recent
          GROUP BY
            ts
              - INTERVAL SECOND(ts) SECOND
              - INTERVAL (MINUTE(ts) %% 10) MINUTE
        """ % (columns_listing)
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_report_sample_recent_aggregated view created")


def create_report_minmax_views():
    """
    Generate min/max values view for the report views.
    These are used by the chart labels views and the chart views.
    """

    all_columns = report_columns

    min_columns_listing = ",\n".join(["MIN(%s) AS %s_min" % (column_name, column_name,) for column_name in all_columns])
    max_columns_listing = ",\n".join(["MAX(%s) AS %s_max" % (column_name, column_name,) for column_name in all_columns])
    round_digits_columns_listing = ",\n".join(["GREATEST(1, IFNULL(CEIL(-LOG(MAX(%s)-MIN(%s))), 0)) AS %s_round_digits" % (column_name, column_name, column_name,) for column_name in all_columns])

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_${view_name_extension}_minmax AS
          SELECT
            COUNT(*) AS count_rows,
            MIN(ts) AS ts_min,
            MAX(ts) AS ts_max,
            TIMESTAMPDIFF(SECOND, MIN(TS), MAX(ts)) AS ts_diff_seconds,
            %s,
            %s,
            %s
          FROM
            ${database_name}.sv_report_${input_view_extension}
        """ % (min_columns_listing, max_columns_listing, round_digits_columns_listing)
    query = query.replace("${database_name}", database_name)

    input_views_extensions = {
        "sample_recent": "sample_recent_aggregated",
        "hour_recent":   "hour_recent",
        "day_recent":    "day_recent",
        "24_7":    "24_7",
        }
    for view_name_extension in input_views_extensions:
        input_view_extension = input_views_extensions[view_name_extension]
        custom_query = query
        custom_query = custom_query.replace("${input_view_extension}", input_view_extension)
        custom_query = custom_query.replace("${view_name_extension}", view_name_extension)
        act_query(custom_query)

    verbose("reports minmax views created")


def create_report_chart_sample_timeseries_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_chart_sample_timeseries AS
          SELECT
            ts_min
              - INTERVAL SECOND(ts_min) SECOND
              - INTERVAL (MINUTE(ts_min) % 10) MINUTE
              + INTERVAL (numbers.n*10) MINUTE
              AS timeseries_ts,
            numbers.n AS timeseries_key,
            sv_report_sample_recent_aggregated.*
          FROM
            ${database_name}.numbers
            JOIN ${database_name}.sv_report_sample_recent_minmax
            LEFT JOIN ${database_name}.sv_report_sample_recent_aggregated ON (
              ts_min
                - INTERVAL SECOND(ts_min) SECOND
                - INTERVAL (MINUTE(ts_min) % 10) MINUTE
                + INTERVAL (numbers.n*10) MINUTE
              = ts
            )
          WHERE
            numbers.n <= TIMESTAMPDIFF(MINUTE, ts_min, ts_max)/10 + 1
            AND ts_min
              - INTERVAL SECOND(ts_min) SECOND
              - INTERVAL (MINUTE(ts_min) % 10) MINUTE
              + INTERVAL (numbers.n*10) MINUTE <= ts_max
        """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_report_chart_sample_timeseries view created")


def create_report_chart_hour_timeseries_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_chart_hour_timeseries AS
          SELECT
            ts_min
              + INTERVAL numbers.n HOUR
              AS timeseries_ts,
            numbers.n AS timeseries_key,
            sv_report_hour_recent.*
          FROM
            ${database_name}.numbers
            JOIN ${database_name}.sv_report_hour_recent_minmax
            LEFT JOIN ${database_name}.sv_report_hour_recent ON (
              ts_min
                + INTERVAL numbers.n HOUR
              = ts
            )
          WHERE
            numbers.n <= TIMESTAMPDIFF(HOUR, ts_min, ts_max) + 1
            AND ts_min
              + INTERVAL numbers.n HOUR <= ts_max
        """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_report_chart_hour_timeseries view created")


def create_report_chart_day_timeseries_view():
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_chart_day_timeseries AS
          SELECT
            ts_min
              + INTERVAL numbers.n DAY
              AS timeseries_ts,
            numbers.n AS timeseries_key,
            sv_report_day_recent.*
          FROM
            ${database_name}.numbers
            JOIN ${database_name}.sv_report_day_recent_minmax
            LEFT JOIN ${database_name}.sv_report_day_recent ON (
              ts_min
                + INTERVAL numbers.n DAY
              = ts
            )
          WHERE
            numbers.n <= TIMESTAMPDIFF(DAY, ts_min, ts_max) + 1
            AND ts_min
              + INTERVAL numbers.n DAY <= ts_max
        """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_report_chart_day_timeseries view created")


def create_report_chart_labels_views():
    """
    Generate x-axis labels for the google api report views
    """

    title_ts_formats = {
        "sample": "%b %e, %H:%i",
        "hour":   "%b %e, %H:00",
        "day":    "%b %e, %Y",
        }
    title_descriptions = {
        "sample": ("ROUND(TIMESTAMPDIFF(MINUTE, ts_min, ts_max)/60)", "hours"),
        "hour":   ("ROUND(TIMESTAMPDIFF(HOUR, ts_min, ts_max)/24)", "days"),
        "day":    ("ROUND(TIMESTAMPDIFF(HOUR, ts_min, ts_max)/24)", "days"),
        }
    ts_formats = {
        "sample": "%H:00",
        "hour":   "%D",
        "day":    "%b %e",
        }
    labels_times = {
        "sample": ("DATE(ts_min) + INTERVAL HOUR(ts_min) HOUR", "HOUR"),
        "hour":   ("DATE(ts_min)", "DAY"),
        "day":    ("DATE(ts_min) - INTERVAL WEEKDAY(ts_min) DAY", "WEEK"),
        }
    labels_step_and_limits = {
        "sample": ("HOUR", 4, 24),
        "hour":   ("DAY", 1, 10),
        "day":    ("DAY", 1, 52),
        }
    ts_step_seconds_map = {
        "sample": 60*10,
        "hour":   60*60,
        "day":    60*60*24,
        }
    x_axis_map = {
        "sample": ("ROUND(60*100/TIMESTAMPDIFF(MINUTE, ts_min, ts_max), 2)", "ROUND(((60 - MINUTE(ts_min)) MOD 60)*100/TIMESTAMPDIFF(MINUTE, ts_min, ts_max), 2)"),
        "hour":   ("ROUND(24*100/TIMESTAMPDIFF(HOUR, ts_min, ts_max), 2)", "ROUND(((24 - HOUR(ts_min)) MOD 24)*100/TIMESTAMPDIFF(HOUR, ts_min, ts_max) ,2)"),
        "day":    ("ROUND(7*100/TIMESTAMPDIFF(DAY, ts_min, ts_max), 2)", "ROUND(((7 - WEEKDAY(ts_min)) MOD 7)*100/TIMESTAMPDIFF(DAY, ts_min, ts_max) ,2)"),
        }
    stale_error_conditions = {
        "sample": "ts_max < NOW() - INTERVAL 1 HOUR",
        "hour":   "ts_max < NOW() - INTERVAL 2 HOUR",
        "day":    "ts_max < NOW() - INTERVAL 1 DAY",
        }

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_chart_${view_name_extension}_labels AS
          SELECT
            IFNULL(${x_axis_step_size}, '') AS x_axis_step_size,
            IFNULL(${x_axis_offset}, '') AS x_axis_offset,
            IFNULL(
              GROUP_CONCAT(
                IF(${label_function}(${base_ts} + INTERVAL numbers.n ${interval_unit}) % ${labels_step} = 0,
                  LOWER(DATE_FORMAT(${base_ts} + INTERVAL numbers.n ${interval_unit}, '${ts_format}')),
                  IF(${label_function}(${base_ts} + INTERVAL numbers.n ${interval_unit}) % ${labels_step} = ${labels_step}/2,
                    ' ', ''
                  )
                )
                SEPARATOR '|'),
              '') AS x_axis_labels,
            IFNULL(
              GROUP_CONCAT(
                ${x_axis_offset} + (${x_axis_step_size})*IF(${base_ts} < ts_min, n-1, n)
                SEPARATOR ','),
              '') AS x_axis_labels_positions,
            CONCAT(IF (${stale_error_condition}, 'STALE DATA! ', 'Latest '), ${title_numeric_description}, ' ${title_unit_description}: ',
              DATE_FORMAT(ts_min, '${title_ts_format}'), '  -  ', DATE_FORMAT(ts_max, '${title_ts_format}')) AS chart_time_description,
            ${ts_step_seconds} AS ts_step_seconds,
            IF (${stale_error_condition}, '808080', '303030') AS chart_title_color,
            IF (${stale_error_condition}, 'f0f0f0', 'ffffff') AS chart_bg_color
          FROM
            ${database_name}.sv_report_${view_name_extension}_recent_minmax, ${database_name}.numbers
          WHERE
            ${base_ts} + INTERVAL numbers.n ${interval_unit} >= ts_min
            AND ${base_ts} + INTERVAL numbers.n ${interval_unit} <= ts_max
            AND numbers.n <= ${labels_limit}
          GROUP BY
            sv_report_${view_name_extension}_recent_minmax.ts_min, sv_report_${view_name_extension}_recent_minmax.ts_max 
        """
    query = query.replace("${database_name}", database_name)

    for view_name_extension in ["sample", "hour", "day"]:
        title_ts_format = title_ts_formats[view_name_extension]
        title_numeric_description, title_unit_description = title_descriptions[view_name_extension]
        base_ts, interval_unit = labels_times[view_name_extension]
        ts_step_seconds = ts_step_seconds_map[view_name_extension]
        ts_format = ts_formats[view_name_extension]
        label_function, labels_step, labels_limit = labels_step_and_limits[view_name_extension]
        x_axis_step_size, x_axis_offset = x_axis_map[view_name_extension]
        stale_error_condition = stale_error_conditions[view_name_extension]
        custom_query = query
        custom_query = custom_query.replace("${view_name_extension}", view_name_extension)
        custom_query = custom_query.replace("${base_ts}", base_ts)
        custom_query = custom_query.replace("${title_ts_format}", title_ts_format)
        custom_query = custom_query.replace("${title_numeric_description}", title_numeric_description)
        custom_query = custom_query.replace("${title_unit_description}", title_unit_description)
        custom_query = custom_query.replace("${interval_unit}", interval_unit)
        custom_query = custom_query.replace("${ts_step_seconds}", "%d" % ts_step_seconds)
        custom_query = custom_query.replace("${ts_format}", str(ts_format))
        custom_query = custom_query.replace("${labels_step}", str(labels_step))
        custom_query = custom_query.replace("${label_function}", label_function)
        custom_query = custom_query.replace("${labels_limit}", str(labels_limit))
        custom_query = custom_query.replace("${x_axis_step_size}", str(x_axis_step_size))
        custom_query = custom_query.replace("${x_axis_offset}", str(x_axis_offset))
        custom_query = custom_query.replace("${stale_error_condition}", stale_error_condition)
        act_query(custom_query)

    verbose("report charts labels views created")


def generate_google_chart_query(chart_columns, alias, scale_from_0=False, scale_to_100=False, chart_colors = []):
    chart_columns_list = [column_name.strip() for column_name in chart_columns.lower().split(",")]

    chart_column_min_listing = ",".join(["%s_min" % column_name for column_name in chart_columns_list])
    chart_column_max_listing = ",".join(["%s_max" % column_name for column_name in chart_columns_list])

    if scale_from_0:
        least_value_clause = "LEAST(0,%s)" % chart_column_min_listing
    elif len(chart_columns_list) > 1:
        least_value_clause = "LEAST(%s)" % chart_column_min_listing
    else:
        # Sadly, LEAST doesn;t work for 1 argument only... So we need a special case here
        least_value_clause = chart_column_min_listing

    if scale_to_100:
        greatest_value_clause = "GREATEST(100,%s)" % chart_column_max_listing
    elif len(chart_columns_list) > 1:
        greatest_value_clause = "GREATEST(%s)" % chart_column_max_listing
    else:
        # Sadly, LEAST doesn;t work for 1 argument only... So we need a special case here
        greatest_value_clause = chart_column_max_listing


    piped_chart_column_listing = "|".join(chart_columns_list)

    chart_colors = [chart_color.replace("#", "") for chart_color in chart_colors]
    chart_colors = None
    if (not chart_colors) or (len(chart_colors) < len(chart_columns_list)):
        chart_colors = ["ff8c00", "4682b4", "9acd32", "dc143c", "9932cc", "ffd700", "191970", "7fffd4", "808080", "dda0dd"]
    chart_colors = chart_colors[0:len(chart_columns_list)]

    # '_' is used for missing (== NULL) values.
    column_values = [ """
        GROUP_CONCAT(
          IFNULL(
            SUBSTRING(
              charts_api.simple_encoding,
              1+ROUND(
                61 *
                (%s - IFNULL(${least_value_clause}, 0))/(IFNULL(${greatest_value_clause}, 0) - IFNULL(${least_value_clause}, 0))
              )
            , 1)
          , '_')
          ORDER BY timeseries_key ASC
          SEPARATOR ''
        ),
        """ % (column_name) for column_name in chart_columns_list
    ]
    concatenated_column_values = "',',".join(column_values)

    # '_' is used for missing (== NULL) values.
    # Here's an ugly patch: MySQL's ROUND rounds up a number, but can leave the trailing zeros.
    # How to overcome this? 
    # Tried using ROUND() (there's a bug). Tried using FORMAT (5.0 only accepts constants).
    # I do manual parsing of the number as text... :(
    # Trick for overcoming group_concat_max_len=1024, as is the default: CONCAT several conditional GROUP_CONCATs
    column_values_extended = [ """
        CONCAT(
          GROUP_CONCAT(
            IF (timeseries_key BETWEEN 0 AND 79,
              CONCAT(
                IF (timeseries_key > 0, ',', ''),
                IFNULL(CONCAT(TRUNCATE(${column_name}, 0), SUBSTRING(${column_name} - TRUNCATE(${column_name}, 0), 2, ${column_name}_round_digits+1)), '_')
              ),
              ''
            )  
            ORDER BY timeseries_key ASC
            SEPARATOR ''
          ),
          GROUP_CONCAT(
            IF (timeseries_key BETWEEN 80 AND 159,
              CONCAT(',',
                IFNULL(CONCAT(TRUNCATE(${column_name}, 0), SUBSTRING(${column_name} - TRUNCATE(${column_name}, 0), 2, ${column_name}_round_digits+1)), '_')
              ),
              ''
            )  
            ORDER BY timeseries_key ASC
            SEPARATOR ''
          ),
          GROUP_CONCAT(
            IF (timeseries_key >= 160,
              CONCAT(',',
                IFNULL(CONCAT(TRUNCATE(${column_name}, 0), SUBSTRING(${column_name} - TRUNCATE(${column_name}, 0), 2, ${column_name}_round_digits+1)), '_')
              ),
              ''
            )  
            ORDER BY timeseries_key ASC
            SEPARATOR ''
          )
        ),
        """.replace("${column_name}", column_name) for column_name in chart_columns_list
    ]
    concatenated_column_values_extended = "'|',".join(column_values_extended)
    
    # For each chart type, we create two columns: one with a simple-format Google chart, another with a semi-text-format.
    # The latter is to be used with openark-charts, is considerably longer (way more than the permitted 2048 characters in a URL),
    # and is not entirely Google-compliant. So it's tailor made.
    chart_query_template = """
        REPLACE(
          CONCAT(
            CONVERT(charts_api.service_url USING utf8), '?cht=lc&chs=', charts_api.chart_width, 'x', charts_api.chart_height, '&chts=', chart_title_color, ',12&chtt=',
            chart_time_description, '&chf=c,s,', chart_bg_color,
            '&chdl=${piped_chart_column_listing}&chdlp=b&chco=${chart_colors}&chd=${encoding_type}:', ${column_values}
            '&chxt=x,y&chxr=1,', ${least_value_clause},',', ${greatest_value_clause}, '&chxl=0:|', x_axis_labels, '|&chxs=0,505050,10,0,lt',
            '&chg=', x_axis_step_size, ',25,1,2,', x_axis_offset, ',0',
            '&chxp=0,', x_axis_labels_positions,
            '&tsstart=', ts_min, '&tsstep=', ts_step_seconds
          ), ' ', '+') AS ${alias}
        """
    query = """%s, %s""" % (
        chart_query_template.replace("${encoding_type}", "s").replace("${column_values}", concatenated_column_values).replace("${alias}", alias),
        chart_query_template.replace("${encoding_type}", "t").replace("${column_values}", concatenated_column_values_extended).replace("${alias}", "%s_extended" % alias)
        )

    query = query.replace("${database_name}", database_name)
    query = query.replace("${piped_chart_column_listing}", piped_chart_column_listing)
    query = query.replace("${chart_colors}", ",".join(chart_colors))
    query = query.replace("${least_value_clause}", least_value_clause)
    query = query.replace("${greatest_value_clause}", greatest_value_clause)

    return query


def create_report_google_chart_views(charts_list):
    for view_name_extension in ["sample", "hour", "day"]:
        charts_queries = [generate_google_chart_query(chart_columns, alias, scale_from_0, scale_to_100, chart_colors) for (chart_columns, alias, scale_from_0, scale_to_100, chart_colors) in charts_list]
        charts_query = ",".join(charts_queries)
        query = """
            CREATE
            OR REPLACE
            ALGORITHM = TEMPTABLE
            DEFINER = CURRENT_USER
            SQL SECURITY INVOKER
            VIEW ${database_name}.sv_report_chart_${view_name_extension} AS
              SELECT
                %s
              FROM
                ${database_name}.sv_report_chart_${view_name_extension}_timeseries, ${database_name}.sv_report_${view_name_extension}_recent_minmax, ${database_name}.charts_api, ${database_name}.sv_report_chart_${view_name_extension}_labels
            """ % charts_query
        query = query.replace("${database_name}", database_name)
        query = query.replace("${view_name_extension}", view_name_extension)
        act_query(query)

    verbose("report charts views created")


def create_custom_google_charts_views():
    chart_type_extensions = {
            "value": "",
            "value_psec": "_psec",
            "time": "_time",
        }
    simple_chart_case_clauses = []
    extended_chart_case_clauses = []
    if get_custom_query_ids():
        for i in get_custom_query_ids():
            for chart_type in ["value", "value_psec", "time"]:
                simple_chart_case_clauses.append("WHEN '%d,%s' THEN custom_%d%s" % (i, chart_type, i, chart_type_extensions[chart_type]))
                extended_chart_case_clauses.append("WHEN '%d,%s' THEN custom_%d%s_extended" % (i, chart_type, i, chart_type_extensions[chart_type]))
    else:
        # No point in this while view; just make a dummy statement
        simple_chart_case_clauses.append("WHEN NULL THEN NULL");
        extended_chart_case_clauses.append("WHEN NULL THEN NULL");
    for view_name_extension in ["sample", "hour", "day"]:
        query = """
            CREATE
            OR REPLACE
            ALGORITHM = TEMPTABLE
            DEFINER = CURRENT_USER
            SQL SECURITY INVOKER
            VIEW ${database_name}.sv_custom_chart_${view_name_extension} AS
              SELECT
                custom_query_view.*,
                CASE CONCAT(custom_query_id, ',', chart_type)
                    %s
                    ELSE NULL
                END AS chart,
                CASE CONCAT(custom_query_id, ',', chart_type)
                    %s
                    ELSE NULL
                END AS chart_extended
              FROM
                ${database_name}.custom_query_view, ${database_name}.sv_report_chart_${view_name_extension}
              WHERE
                ${database_name}.custom_query_view.chart_enabled = 1
              ORDER BY
                chart_order ASC, custom_query_id ASC
            """ % ("\n".join(simple_chart_case_clauses), "\n".join(extended_chart_case_clauses),)
        query = query.replace("${database_name}", database_name)
        query = query.replace("${view_name_extension}", view_name_extension)
        act_query(query)

    verbose("custom chart views created")


def create_custom_google_charts_flattened_views():
    """
    We flatten the sv_custom_chart_* views into one row. This will be useful when generating HTML view.
    """
    custom_clauses = []
    
    if get_custom_query_ids_charts_enabled():
        for i in get_custom_query_ids_charts_enabled():
            custom_clause = """
                MAX(IF(custom_query_id=%d AND enabled, chart, NULL)) AS custom_%d_chart,
                MAX(IF(custom_query_id=%d AND enabled, chart_extended, NULL)) AS custom_%d_chart_extended,
                MAX(IF(custom_query_id=%d, chart_name, NULL)) AS custom_%d_chart_name,
                MAX(IF(custom_query_id=%d, description, NULL)) AS custom_%d_text_description,
                MAX(IF(custom_query_id=%d, CONCAT(description, ' [', chart_type, ']'), NULL)) AS custom_%d_description
                """ % (i, i, i, i, i, i, i, i, i, i,)
            custom_clauses.append(custom_clause)
    else:
        # No point in this whole view. Add a dummy column
        custom_clauses.append("MAX(NULL) AS NA")
        
    for view_name_extension in ["sample", "hour", "day"]:
        query = """
            CREATE
            OR REPLACE
            ALGORITHM = TEMPTABLE
            DEFINER = CURRENT_USER
            SQL SECURITY INVOKER
            VIEW ${database_name}.sv_custom_chart_flattened_${view_name_extension} AS
              SELECT
                %s
              FROM
                ${database_name}.sv_custom_chart_${view_name_extension}
            """ % ", ".join(custom_clauses)
        query = query.replace("${database_name}", database_name)
        query = query.replace("${view_name_extension}", view_name_extension)
        act_query(query)

    verbose("custom chart flattened views created")


def create_report_html_view(charts_aliases):
    charts_aliases_list = [chart_alias.strip() for chart_alias in charts_aliases.split(",")]

    rows_queries = []
    js_queries = []
    for chart_alias in charts_aliases_list:
        div_queries = []
        for view_name_extension in ["sample", "hour", "day"]:
            div_query = """'<div class="chart_container">
                    <div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>
                    <h3>', IFNULL(CONCAT('<a href="', sv_report_chart_${view_name_extension}.${chart_alias}, '">[url]</a>'), 'N/A'), '</h3>
                    <div id="chart_div_${chart_alias}_${view_name_extension}" class="chart"></div>
                </div>'
                """
            div_query = div_query.replace("${chart_alias}", chart_alias)
            div_query = div_query.replace("${view_name_extension}", view_name_extension)
            div_queries.append(div_query)

            js_query = """IFNULL(
                    CONCAT('
                        new openark_lchart(
                            document.getElementById("chart_div_${chart_alias}_${view_name_extension}"), 
                            {width: ', chart_width, ', height: ',  chart_height, '}
                            ).read_google_url("', sv_report_chart_${view_name_extension}.${chart_alias}_extended, '");
                        '),
                    '')
                """ 
            js_query = js_query.replace("${chart_alias}", chart_alias)
            js_query = js_query.replace("${view_name_extension}", view_name_extension)
            js_queries.append(js_query)

        row_query = """
            '<div class="row">
                <a name="${chart_alias}"></a>
                <h2>${chart_alias} <a href="#">[top]</a><!--mcp_http <a href="zoom/${chart_alias}">[zoom]</a> mcp_http--></h2>',
                %s,
                '<div class="clear"></div>',
            '</div>
                ',
            """ % "".join(div_queries)
        row_query = row_query.replace("${chart_alias}", chart_alias)
        rows_queries.append(row_query)
    all_charts_query = "".join(rows_queries)

    chart_aliases_map = " | ".join(["""<a href="#%s">%s</a>""" % (chart_alias, chart_alias,) for chart_alias in charts_aliases_list])
    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_html AS
          SELECT CONCAT('
            <html>
                <head>
                <title>', metadata.database_name, ' monitoring: full report</title>
                <!--[if IE]>
                    <xml:namespace ns="urn:schemas-microsoft-com:vml" prefix="v" />
                    <style> v\\\\:* { behavior: url(#default#VML); }</style >
                <![endif]-->
                <meta http-equiv="refresh" content="7200" />
                <style type="text/css">
                    ', common_css, '
                    div.header {
                        position: relative;
                        float: left;
                        background: #ffffff;
                        width: ', ((chart_width+20)*3 + 20), ';
                    }
                    div.row {
                        width: ', ((chart_width+30)*3), ';
                    }
                    div.chart {
                        white-space: nowrap;
                        width: ', chart_width, 'px;
                    }
                    div.chart_container {
                        position: relative;
                        float: left;
                        white-space: nowrap;
                        padding: 10px;
                        background: #ffffff;
                        width: ', charts_api.chart_width, ';
                        margin-right: 10px;
                        margin-bottom: 10px;
                    }
                </style>
                <script type="text/javascript" charset="utf-8">
                    ', openark_lchart, '
                </script>
                <script type="text/javascript" charset="utf-8">
                    window.onload = function () {
                ', %s, '
                    };
                </script>
                </head>
                <body>
                    <a name=""></a>
                    <div class="header">
                        <div class="corner bl"></div><div class="corner br"></div>
                        <div class="header_content">
                            <h1><strong class="db">', metadata.database_name, '</strong> database monitoring: 24 hours / 10 days / history report</h1>
                            Report generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on <strong>',
                                DATE_FORMAT(NOW(),'%%b %%D %%Y, %%H:%%i'), '</strong>. Revision: <strong>', metadata.revision, '</strong>, build: <strong>', metadata.build, '</strong>. MySQL version: <strong>', metadata.mysql_version, '</strong>    
                            <br/>The charts on this report are generated locally and do not send data over the net. Click the <a name="none">[url]</a> links to view Google image charts.
                            <hr/>
                            Navigate: ${chart_aliases_map}
                        </div>
                    </div>
                    <div class="clear"></div>
                    ',
                    %s '
                </body>
            </html>
          ') AS html
          FROM
            ${database_name}.sv_report_chart_sample, 
            ${database_name}.sv_report_chart_hour, 
            ${database_name}.sv_report_chart_day, 
            ${database_name}.metadata, 
            ${database_name}.charts_api,
            ${database_name}.html_components
        """ % (",".join(js_queries), all_charts_query)
    query = query.replace("${database_name}", database_name)
    query = query.replace("${chart_aliases_map}", chart_aliases_map)
    query = query.replace("${corners_image}", corners_image.replace("'","''"))
    act_query(query)

    verbose("report html view created")


def create_report_html_brief_view(report_charts):
    charts_sections_list = [chart_section for (chart_section, charts_aliases) in report_charts]
    chart_aliases_navigation_map = " | ".join(["""<a href="#%s">%s</a>""" % (chart_section, chart_section) for chart_section in charts_sections_list if chart_section])

    sections_queries = []
    js_queries = []
    for (chart_section, charts_aliases) in report_charts:
        charts_aliases_list = [chart_alias.strip() for chart_alias in charts_aliases.split(",")]
        charts_aliases_queries = []
        for chart_alias in charts_aliases_list:
            # There's different treatment to custom columns:
            # Custom columns' titles need to reflect the custom query's description. So does the chart's legend.
            custom_query_id = get_custom_query_id_by_column_name(chart_alias)
            div_query = """'<div class="chart_container">
                    <div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>
                    <h3>${chart_alias_header} ', 
                        IFNULL(
                            CONCAT('<a href="', ${chart_alias_url_simple}, '">[url]</a>')
                        , '[N/A]'), 
                    '<!--mcp_http <a href="zoom/${chart_alias}">[zoom]</a> mcp_http--></h3>
                    <div id="chart_div_${chart_alias}" class="chart"></div>
                </div>',
                """
            div_query = div_query.replace("${chart_alias}", chart_alias)
            if custom_query_id is None:
                # Normal column
                chart_alias_url_simple = chart_alias
                chart_alias_url_extended = "%s_extended" % chart_alias
                div_query = div_query.replace("${chart_alias_header}", chart_alias.replace("_", " "))
            else:
                # This is a custom column
                chart_alias_url = "REPLACE(%s, '&chdl=custom_', CONCAT('&chdl=', IFNULL(CONCAT(REPLACE(custom_%d_text_description, ' ', '+'), ':+'), ''), 'custom_'))"
                chart_alias_url_simple = chart_alias_url % (chart_alias, custom_query_id,)
                chart_alias_url_extended = chart_alias_url % ("%s_extended" % chart_alias, custom_query_id,)
                div_query = div_query.replace("${chart_alias_header}", "', custom_%d_text_description, '" % custom_query_id)
            div_query = div_query.replace("${chart_alias_url_simple}", chart_alias_url_simple)
            charts_aliases_queries.append(div_query)

            js_query = """IFNULL(
                    CONCAT('
                        new openark_lchart(
                            document.getElementById("chart_div_${chart_alias}"), 
                            {width: ', chart_width, ', height: ',  chart_height, '}
                            ).read_google_url("', ${chart_alias_url_extended}, '");
                        '),
                    '')
                """ 
            js_query = js_query.replace("${chart_alias}", chart_alias)
            js_query = js_query.replace("${chart_alias_url_extended}", chart_alias_url_extended)
            js_queries.append(js_query)
        charts_aliases_query = "".join(charts_aliases_queries)
        
        chart_section_anchor = chart_section 
        if not chart_section:
            chart_section_anchor = "section_%d" % len(sections_queries)
        section_query = """'
            <a name="%s"></a>
            <h2>%s <a href="#">[top]</a></h2>
            
            <div class="row">',
                %s
                '<div class="clear"></div>
            </div>
                ',
            """ % (chart_section_anchor, chart_section, charts_aliases_query)
        sections_queries.append(section_query)


    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_html_brief AS
          SELECT CONCAT('
            <html>
                <head>
                    <title>', metadata.database_name, ' monitoring: latest 24 hours report</title>
                    <meta http-equiv="refresh" content="600" />
                    <!--[if IE]>
                        <xml:namespace ns="urn:schemas-microsoft-com:vml" prefix="v" />
                        <style> v\\\\:* { behavior: url(#default#VML); }</style >
                    <![endif]-->
                    <style type="text/css">
                        ', common_css, '
                        div.row {
                            width: ', ((chart_width+30)*3), ';
                        }
                        div.chart {
                            white-space: nowrap;
                            width: ', chart_width, 'px;
                        }
                        div.chart_container {
                            position: relative;
                            float: left;
                            white-space: nowrap;
                            padding: 10px;
                            background: #ffffff;
                            width: ', charts_api.chart_width, ';
                            height: ', (charts_api.chart_height+155), ';
                            margin-right: 10px;
                            margin-bottom: 10px;
                        }
                        div.header {
                            position: relative;
                            float: left;
                            background: #ffffff;
                            width: ', ((chart_width+20)*3 + 20), ';
                        }
                    </style>
                    <script type="text/javascript" charset="utf-8">
                        ', openark_lchart, '
                    </script>
                    <script type="text/javascript" charset="utf-8">
                        window.onload = function () {
                    ', %s, '
                        };
                    </script>
                </head>
                <body>
                    <a name=""></a>
                    <div class="header">
                        <div class="corner bl"></div><div class="corner br"></div>
                        <div class="header_content">
                            <h1><strong class="db">', metadata.database_name, '</strong> database monitoring: latest 24 hours report</h1>
                            Report generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on <strong>',
                                DATE_FORMAT(NOW(),'%%b %%D %%Y, %%H:%%i'), '</strong>. Revision: <strong>', metadata.revision, '</strong>, build: <strong>', metadata.build, '</strong>. MySQL version: <strong>', metadata.mysql_version, '</strong>    
                            <br/>The charts on this report are generated locally and do not send data over the net. Click the <a name="none">[url]</a> links to view Google image charts.
                            <hr/>
                            Navigate: ${chart_aliases_navigation_map}
                        </div>
                    </div>
                    <div class="clear"></div>
                    ',
                    %s '
                </body>
            </html>
          ') AS html
          FROM
            ${database_name}.sv_report_chart_sample, 
            ${database_name}.sv_custom_chart_flattened_sample, 
            ${database_name}.charts_api,
            ${database_name}.html_components,
            ${database_name}.metadata
        """ % (",".join(js_queries), "".join(sections_queries))
    query = query.replace("${database_name}", database_name)
    query = query.replace("${chart_aliases_navigation_map}", chart_aliases_navigation_map)
    query = query.replace("${global_width}", str(options.chart_width*3 + 30))
    query = query.replace("${corners_image}", corners_image.replace("'","''"))

    act_query(query)

    verbose("sv_report_html_brief created")


def create_custom_html_view():
    rows_queries = []
    js_queries = []
    for i in get_custom_query_ids_charts_enabled():
        chart_alias = "custom_%d_chart" % i
        div_queries = []
        for view_name_extension in ["sample", "hour", "day"]:
            div_query = """'<div class="chart_container">
                    <div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>
                    <h3>', 
                        IFNULL(
                            CONCAT('<a href="', 
                                REPLACE(
                                    sv_custom_chart_flattened_${view_name_extension}.${chart_alias}, 
                                    '&chdl=custom_', 
                                    CONCAT(
                                        '&chdl=', 
                                        IFNULL(
                                            CONCAT(
                                                REPLACE(sv_custom_chart_flattened_${view_name_extension}.custom_%d_text_description, ' ', '+'), 
                                                ':+'), 
                                            ''), 
                                        'custom_')
                                )
                            , '">[url]</a>'), 
                        'N/A'), '</h3>
                    <div id="chart_div_${chart_alias}_${view_name_extension}" class="chart"></div>
                </div>'
                """ % i
            div_query = div_query.replace("${chart_alias}", chart_alias)
            div_query = div_query.replace("${view_name_extension}", view_name_extension)
            div_queries.append(div_query)

            js_query = """IFNULL(
                    CONCAT('
                        new openark_lchart(
                            document.getElementById("chart_div_${chart_alias}_${view_name_extension}"), 
                            {width: ', chart_width, ', height: ',  chart_height, '}
                            ).read_google_url("', 
                                REPLACE(
                                    sv_custom_chart_flattened_${view_name_extension}.${chart_alias}_extended, 
                                    '&chdl=custom_', 
                                    CONCAT(
                                        '&chdl=', 
                                        IFNULL(
                                            CONCAT(
                                                REPLACE(sv_custom_chart_flattened_${view_name_extension}.custom_%d_text_description, ' ', '+'), 
                                                ':+'), 
                                            ''), 
                                        'custom_')
                                )
                            , '");
                        '),
                    ''),
                """ % i
            js_query = js_query.replace("${chart_alias}", chart_alias)
            js_query = js_query.replace("${view_name_extension}", view_name_extension)
            js_queries.append(js_query)

        row_query = """
            '<div class="row">
                <a name="${chart_alias}"></a>
                <h2>', sv_custom_chart_flattened_${view_name_extension}.custom_%d_description,
                ': ${chart_alias} <a href="#">[top]</a><!--mcp_http <a href="zoom/', sv_custom_chart_flattened_${view_name_extension}.custom_%d_chart_name,
                '">[zoom]</a> mcp_http--></h2>',
                %s,
                '<div class="clear"></div>',
            '</div>
                ',
            """ % (i, i, "".join(div_queries))
        row_query = row_query.replace("${chart_alias}", chart_alias)
        row_query = row_query.replace("${view_name_extension}", view_name_extension)
        rows_queries.append(row_query)
    all_charts_query = "".join(rows_queries)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_custom_html AS
          SELECT CONCAT('
            <html>
                <head>
                <title>', metadata.database_name, ' monitoring: full custom report</title>
                <!--[if IE]>
                    <xml:namespace ns="urn:schemas-microsoft-com:vml" prefix="v" />
                    <style> v\\\\:* { behavior: url(#default#VML); }</style >
                <![endif]-->
                <meta http-equiv="refresh" content="7200" />
                <style type="text/css">
                    ', common_css, '
                    div.header {
                        position: relative;
                        float: left;
                        background: #ffffff;
                        width: ', ((chart_width+20)*3 + 20), ';
                    }
                    div.row {
                        width: ', ((chart_width+30)*3), ';
                    }
                    div.chart {
                        white-space: nowrap;
                        width: ', chart_width, 'px;
                    }
                    div.chart_container {
                        position: relative;
                        float: left;
                        white-space: nowrap;
                        padding: 10px;
                        background: #ffffff;
                        width: ', charts_api.chart_width, ';
                        margin-right: 10px;
                        margin-bottom: 10px;
                    }
                </style>
                <script type="text/javascript" charset="utf-8">
                    ', openark_lchart, '
                </script>
                <script type="text/javascript" charset="utf-8">
                    window.onload = function () {
                        ', %s '
                    };
                </script>
                </head>
                <body>
                    <a name=""></a>
                    <div class="header">
                        <div class="corner bl"></div><div class="corner br"></div>
                        <div class="header_content">
                            <h1><strong class="db">', metadata.database_name, '</strong> database monitoring: 24 hours / 10 days / history custom report</h1>
                            Report generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on <strong>',
                                DATE_FORMAT(NOW(),'%%b %%D %%Y, %%H:%%i'), '</strong>. Revision: <strong>', metadata.revision, '</strong>, build: <strong>', metadata.build, '</strong>. MySQL version: <strong>', metadata.mysql_version, '</strong>    
                            <br/>The charts on this report are generated locally and do not send data over the net. Click the <a name="none">[url]</a> links to view Google image charts.
                            <hr/>
                            Navigate: ',
                                IFNULL(
                                    custom_query_top_navigation_view.custom_query_top_navigation,
                                    'No custom queries   '), '
                        </div>
                    </div>
                    <div class="clear"></div>
                    ',
                    %s '
                </body>
            </html>
          ') AS html
          FROM
            ${database_name}.sv_custom_chart_flattened_sample, 
            ${database_name}.sv_custom_chart_flattened_hour, 
            ${database_name}.sv_custom_chart_flattened_day, 
            ${database_name}.custom_query_top_navigation_view,
            ${database_name}.metadata,
            ${database_name}.charts_api,
            ${database_name}.html_components
        """ % ("".join(js_queries), all_charts_query)
    query = query.replace("${database_name}", database_name)
    query = query.replace("${corners_image}", corners_image.replace("'","''"))
    act_query(query)

    verbose("sv_custom_html created")


def create_custom_html_brief_view():

    sections_queries = []
    js_queries = []

    charts_aliases_queries = []
    for i in get_custom_query_ids_charts_enabled():
        chart_alias = "custom_%d" % i
        # There's different treatment to custom columns:
        # Custom columns' titles need to reflect the custom query's description. So does the chart's legend.
        custom_query_id = get_custom_query_id_by_column_name(chart_alias)
        div_query = """'<div class="chart_container">
                <div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>
                <h3>${chart_alias_header} ', 
                    IFNULL(
                        CONCAT('<a href="', ${chart_alias_url_simple}, '">[url]</a>')
                    , '[N/A]'), 
                '<!--mcp_http <a href="zoom/', custom_${custom_query_id}_chart_name,
                '">[zoom]</a> mcp_http--></h3>
                <div id="chart_div_${chart_alias}" class="chart"></div>
            </div>',
            """
        div_query = div_query.replace("${chart_alias}", chart_alias)
        div_query = div_query.replace("${custom_query_id}", "%d" % custom_query_id)
        # This is a custom column
        chart_alias_url = "REPLACE(${chart_alias_url_column}, '&chdl=custom_', CONCAT('&chdl=', IFNULL(CONCAT(REPLACE(custom_%d_text_description, ' ', '+'), ':+'), ''), 'custom_'))" % (custom_query_id,)
        chart_alias_url_simple = chart_alias_url.replace("${chart_alias_url_column}", "%s_chart" % chart_alias)
        chart_alias_url_extended = chart_alias_url.replace("${chart_alias_url_column}", "%s_chart_extended" % chart_alias)

        div_query = div_query.replace("${chart_alias_header}", "', custom_%d_description, '" % custom_query_id)
        div_query = div_query.replace("${chart_alias_url_simple}", chart_alias_url_simple)
        charts_aliases_queries.append(div_query)

        js_query = """IFNULL(
                CONCAT('
                    new openark_lchart(
                        document.getElementById("chart_div_${chart_alias}"), 
                        {width: ', chart_width, ', height: ',  chart_height, '}
                        ).read_google_url("', ${chart_alias_url_extended}, '");
                    '),
                ''),
            """ 
        js_query = js_query.replace("${chart_alias}", chart_alias)
        js_query = js_query.replace("${chart_alias_url_extended}", chart_alias_url_extended)
        js_queries.append(js_query)

    charts_aliases_query = "".join(charts_aliases_queries)
    section_query = """
            %s
            '<div class="clear"></div>',
        """ % charts_aliases_query
    sections_queries.append(section_query)


    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_custom_html_brief AS
          SELECT CONCAT('
            <html>
                <head>
                    <title>', metadata.database_name, ' monitoring: latest 24 hours custom report</title>
                    <meta http-equiv="refresh" content="600" />
                    <!--[if IE]>
                        <xml:namespace ns="urn:schemas-microsoft-com:vml" prefix="v" />
                        <style> v\\\\:* { behavior: url(#default#VML); }</style >
                    <![endif]-->
                    <style type="text/css">
                        ', common_css, '
                        div.chart {
                            white-space: nowrap;
                            width: ', chart_width, 'px;
                        }
                        div.chart_container {
                            position: relative;
                            float: left;
                            white-space: nowrap;
                            padding: 10px;
                            background: #ffffff;
                            width: ', charts_api.chart_width, ';
                            height: ', (charts_api.chart_height+155), ';
                            margin-right: 10px;
                            margin-bottom: 10px;
                        }
                        div.header {
                            position: relative;
                            float: left;
                            background: #ffffff;
                            margin-bottom: 10px;
                        }
                    </style>
                    <script type="text/javascript" charset="utf-8">
                        ', openark_lchart, '
                    </script>
                    <script type="text/javascript" charset="utf-8">
                        window.onload = function () {
                            ', %s '
                        };
                    </script>
                </head>
                <body>
                    <a name=""></a>
                    <div class="header">
                        <div class="corner bl"></div><div class="corner br"></div>
                        <div class="header_content">
                            <h1><strong class="db">', metadata.database_name, '</strong> database monitoring: latest 24 hours custom report</h1>
                            Report generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on <strong>',
                                DATE_FORMAT(NOW(),'%%b %%D %%Y, %%H:%%i'), '</strong>. Revision: <strong>', metadata.revision, '</strong>, build: <strong>', metadata.build, '</strong>. MySQL version: <strong>', metadata.mysql_version, '</strong>    
                            <br/>The charts on this report are generated locally and do not send data over the net. Click the <a name="none">[url]</a> links to view Google image charts.
                        </div>
                    </div>
                    <div class="clear"></div>
                    ',
                    %s '
                </body>
            </html>
          ') AS html
          FROM
            ${database_name}.sv_custom_chart_flattened_sample, 
            ${database_name}.metadata, 
            ${database_name}.charts_api,
            ${database_name}.html_components
        """ % ("".join(js_queries), "".join(sections_queries))
    query = query.replace("${database_name}", database_name)
    query = query.replace("${global_width}", str(options.chart_width*3 + 30))
    query = query.replace("${corners_image}", corners_image.replace("'","''"))

    act_query(query)

    verbose("sv_custom_html_brief created")


def create_status_variables_parameter_change_view():
    global_variables, _diff_columns = get_variables_and_status_columns()

    global_variables_select_listing = ["""
        SELECT ${status_variables_table_alias}2.ts AS ts, '%s' AS variable_name, ${status_variables_table_alias}1.%s AS old_value, ${status_variables_table_alias}2.%s AS new_value
        FROM
          ${database_name}.${status_variables_table_name} AS ${status_variables_table_alias}1
          INNER JOIN ${database_name}.${status_variables_table_name} AS ${status_variables_table_alias}2
          ON (${status_variables_table_alias}1.id = ${status_variables_table_alias}2.id-GREATEST(1, IFNULL(${status_variables_table_alias}2.auto_increment_increment, 1)))
        WHERE ${status_variables_table_alias}2.%s != ${status_variables_table_alias}1.%s
        """ % (column_name, column_name, column_name,
               column_name, column_name,) for column_name in global_variables if column_name != 'timestamp']
    global_variables_select_union = " UNION ALL \n".join(global_variables_select_listing)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_parameter_change_union AS
          %s
    """ % (global_variables_select_union,)
    query = query.replace("${database_name}", database_name)
    query = query.replace("${status_variables_table_name}", table_name)
    query = query.replace("${status_variables_table_alias}", table_name)
    act_query(query)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_param_change AS
          SELECT *
          FROM ${database_name}.sv_parameter_change_union
          ORDER BY ts, variable_name
    """
    query = query.replace("${database_name}", database_name)
    act_query(query)

    verbose("sv_param_change view created")


def create_status_variables_long_format_view():
    global_variables, status_variables = get_variables_and_status_columns()
    all_columns_listing = []
    all_columns_listing.extend(global_variables);
    all_columns_listing.extend(status_variables);
    all_columns_listing.extend(["%s_diff" % (column_name,) for column_name in status_variables])
    all_columns_listing.extend(["%s_psec" % (column_name,) for column_name in status_variables])
    all_columns = ",".join(all_columns_listing)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_long_hour AS
            SELECT
                id, ts,
                SUBSTRING_INDEX(SUBSTRING_INDEX('%s', ',', numbers.n), ',', -1) AS variable_name,
                CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(CONCAT_WS(',', %s), ',', numbers.n), ',', -1) AS UNSIGNED) AS variable_value
            FROM
                ${database_name}.sv_hour,
                ${database_name}.numbers
            WHERE
                numbers.n >= 1 AND numbers.n <= %d
            ORDER BY
                id ASC, variable_name ASC
        """ % (all_columns, all_columns, len(all_columns_listing))
    query = query.replace("${database_name}", database_name)
    act_query(query)


def create_status_variables_aggregated_view():
    global_variables, status_variables = get_variables_and_status_columns()
    all_columns_listing = []
    all_columns_listing.extend(global_variables);
    all_columns_listing.extend(status_variables);
    all_columns = ",".join(all_columns_listing)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = TEMPTABLE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_agg_hour AS
            SELECT
                MIN(id) AS id, MIN(ts) AS min_ts, MAX(ts) AS max_ts,
                SUBSTRING_INDEX(SUBSTRING_INDEX('%s', ',', numbers.n), ',', -1) AS variable_name,
                GROUP_CONCAT(CAST(SUBSTRING_INDEX(SUBSTRING_INDEX(CONCAT_WS(',', %s), ',', numbers.n), ',', -1) AS UNSIGNED) ORDER BY ts ASC) AS variable_values
            FROM
                ${database_name}.sv_hour,
                ${database_name}.numbers
            WHERE
                numbers.n >= 1 AND numbers.n <= %d
            GROUP BY
                variable_name ASC
        """ % (all_columns, all_columns, len(all_columns_listing))
    query = query.replace("${database_name}", database_name)
    act_query(query)


def create_report_views(columns_listing):
    # This is currently an ugly patch (first one in this code...)
    # We need to know which columns have been created in the "report" views, so that we can later build the
    # sv_report_minmax_* views.
    # So we parse the columns. We expect one column per line; we allow for aliasing (" as ")
    # We then store the columns for later use.
    
    # Fix possible empty columns (due to no custom columns):
    # (Convert consequtive commans into a single one, remove trailing comma)
    columns_listing = re.sub(",([\\s]*,)+", ",", columns_listing)
    columns_listing = re.sub(",[\\s]*$", "", columns_listing)
    
    columns_names_list = [column_name for column_name in columns_listing.lower().split("\n")]
    columns_names_list = [column_name.split(" as ")[-1].replace(",","").strip() for column_name in columns_names_list]
    columns_names_list = [column_name for column_name in columns_names_list if column_name]
    report_columns.extend(columns_names_list)

    query = """
        CREATE
        OR REPLACE
        ALGORITHM = MERGE
        DEFINER = CURRENT_USER
        SQL SECURITY INVOKER
        VIEW ${database_name}.sv_report_${view_name_extension} AS
          SELECT
            id,
            ts,
            ts_diff_seconds,
            %s
          FROM
            ${database_name}.sv_${view_name_extension}
    """ % columns_listing
    query = query.replace("${database_name}", database_name)

    for view_name_extension in ["sample", "hour", "day"]:
        custom_query = query.replace("${view_name_extension}", view_name_extension)
        act_query(custom_query)

    verbose("report views created")


def create_status_variables_views_and_aggregations():
    # General status variables views:
    create_status_variables_latest_view()
    create_status_variables_diff_view()
    create_status_variables_sample_view()
    # If aggregation tables are enabled, then the hour and day views rely on aggregation tables rather than on sv_sample
    if not options.skip_aggregation:
        # aggregation is enabled
        if not create_status_variables_hour_aggregation_table():
            upgrade_status_variables_hour_aggregation_table()
        if not create_status_variables_day_aggregation_table():
            upgrade_status_variables_day_aggregation_table()
    create_status_variables_hour_view()
    create_status_variables_day_view()
    create_status_variables_parameter_change_view()

    # Report views:
    create_report_views("""
            uptime,
            LEAST(100, ROUND(100*uptime_diff/NULLIF(ts_diff_seconds, 0), 1)) AS uptime_percent,

            innodb_buffer_pool_size,
            innodb_flush_log_at_trx_commit,
            innodb_buffer_pool_pages_total,
            innodb_buffer_pool_pages_data,
            innodb_buffer_pool_pages_dirty,
            innodb_buffer_pool_pages_misc,
            ROUND(100 - 100*innodb_buffer_pool_pages_free/NULLIF(innodb_buffer_pool_pages_total, 0), 1) AS innodb_buffer_pool_used_percent,
            ROUND(100*innodb_buffer_pool_pages_dirty/NULLIF(innodb_buffer_pool_pages_total, 0), 1) AS innodb_buffer_pool_pages_dirty_percent,
            ROUND(100 - (100*innodb_buffer_pool_reads_diff/NULLIF(innodb_buffer_pool_read_requests_diff, 0)), 2) AS innodb_read_hit_percent,
            innodb_buffer_pool_reads_psec,
            innodb_buffer_pool_pages_flushed_psec,
            innodb_dblwr_writes_psec,
            innodb_log_writes_psec,
            innodb_data_writes_psec - innodb_log_writes_psec - innodb_dblwr_writes_psec AS innodb_data_files_writes_psec,
            innodb_data_reads_psec, 
            innodb_os_log_written_psec,
            ROUND(innodb_os_log_written_psec*60*60/1024/1024, 1) AS innodb_estimated_log_mb_written_per_hour,
            innodb_row_lock_waits_psec,
            innodb_row_lock_current_waits,
            innodb_row_lock_time_psec,
            innodb_buffer_pool_read_ahead_psec,
            innodb_buffer_pool_read_ahead_evicted_psec,

            bytes_sent_psec/1024/1024 AS mega_bytes_sent_psec,
            bytes_received_psec/1024/1024 AS mega_bytes_received_psec,

            key_buffer_size,
            key_reads_diff,
            key_read_requests_diff,
            key_writes_diff,
            key_write_requests_diff,
            key_reads_psec,
            key_read_requests_psec,
            key_writes_psec,
            key_write_requests_psec,
            key_read_requests_psec - key_reads_psec AS key_read_hits_psec, 
            key_write_requests_psec - key_writes_psec AS key_write_hits_psec, 
            ROUND(100 - 100*(key_blocks_unused * key_cache_block_size)/NULLIF(key_buffer_size, 0), 1) AS key_buffer_used_percent,
            ROUND(100 - 100*key_reads_diff/NULLIF(key_read_requests_diff, 0), 1) AS key_read_hit_percent,
            ROUND(100 - 100*key_writes_diff/NULLIF(key_write_requests_diff, 0), 1) AS key_write_hit_percent,

            com_select_psec,
            com_insert_psec,
            com_insert_select_psec,
            com_update_psec,
            com_delete_psec,
            com_replace_psec,
            com_set_option_psec,
            com_commit_psec,
            slow_queries_psec,
            questions_psec,
            queries_psec,
            ROUND(100*com_select_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS com_select_percent,
            ROUND(100*com_insert_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS com_insert_percent,
            ROUND(100*com_insert_select_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS com_insert_select_percent,
            ROUND(100*com_update_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS com_update_percent,
            ROUND(100*com_delete_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS com_delete_percent,
            ROUND(100*com_replace_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS com_replace_percent,
            ROUND(100*com_set_option_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS com_set_option_percent,
            ROUND(100*com_commit_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS com_commit_percent,
            ROUND(100*slow_queries_diff/NULLIF(IFNULL(queries_diff, questions_diff), 0), 1) AS slow_queries_percent,
            long_query_time,
            innodb_rows_read_psec, 
            innodb_rows_inserted_psec, 
            innodb_rows_updated_psec, 
            innodb_rows_deleted_psec,

            handler_read_rnd_psec, 
            handler_read_rnd_next_psec, 
            handler_read_first_psec, 
            handler_read_next_psec, 
            handler_read_prev_psec, 
            handler_read_key_psec,
            
            select_scan_psec,
            select_full_join_psec,
            select_range_psec,
            ROUND(100*select_scan_diff/NULLIF(com_select_diff, 0), 1) AS select_scan_percent,
            ROUND(100*select_full_join_diff/NULLIF(com_select_diff, 0), 1) AS select_full_join_percent,
            ROUND(100*select_range_diff/NULLIF(com_select_diff, 0), 1) AS select_range_percent,
            sort_merge_passes_psec,

            table_locks_waited_psec,
            ROUND(100*table_locks_waited_diff/NULLIF(table_locks_waited_diff + table_locks_immediate_diff, 0), 1) AS table_lock_waited_percent,

            IFNULL(table_cache, 0) + IFNULL(table_open_cache, 0) AS table_cache_size,
            IFNULL(table_definition_cache, 0) AS table_definition_cache_size,
            open_tables,
            IFNULL(open_table_definitions, 0) AS open_table_definitions,            
            ROUND(100*open_tables/NULLIF(IFNULL(table_cache, 0) + IFNULL(table_open_cache, 0), 0), 1) AS table_cache_use_percent,
            opened_tables_psec,
            IFNULL(opened_table_definitions_psec, 0) AS opened_table_definitions_psec,

            tmp_table_size,
            max_heap_table_size,
            created_tmp_tables_psec,
            created_tmp_disk_tables_psec,
            ROUND(100*created_tmp_disk_tables_diff/NULLIF(created_tmp_tables_diff, 0), 1) AS created_disk_tmp_tables_percent,

            max_connections,
            max_used_connections,
            ROUND(100*max_used_connections/NULLIF(max_connections, 0), 1) AS max_connections_used_percent,
            connections_psec,
            aborted_connects_psec,
            ROUND(100*aborted_connects_diff/NULLIF(connections_diff, 0), 1) AS aborted_connections_percent,

            thread_cache_size,
            threads_cached,
            ROUND(100*threads_cached/NULLIF(thread_cache_size, 0), 1) AS thread_cache_used_percent,
            threads_created_psec,
            threads_connected,
            ROUND(100*threads_connected/NULLIF(max_connections, 0), 1) AS threads_connected_used_percent,
            threads_running,

            main_status_file_number,
            main_status_position,
            relay_log_space_limit,
            relay_log_space_limit/1024/1024 AS relay_log_space_limit_mb,
            max_relay_log_size,
            IF(max_relay_log_size = 0, max_binlog_size, max_relay_log_size) AS relay_log_max_size,
            IF(max_relay_log_size = 0, max_binlog_size, max_relay_log_size)/1024/1024 AS relay_log_max_size_mb,
            relay_log_space,
            relay_log_space/1024/1024 AS relay_log_space_mb,
            ROUND(100*relay_log_space/NULLIF(relay_log_space_limit, 0), 1) AS relay_log_space_used_percent,
            seconds_behind_main,
            seconds_behind_main_psec,
            IF(seconds_behind_main_psec >= 0, NULL, FLOOR(-seconds_behind_main/seconds_behind_main_psec)) AS estimated_subordinate_catchup_seconds,

            ROUND((os_loadavg_millis/1000), 2) AS os_loadavg,
            os_total_cpu_cores,
            ROUND(100.0*(os_cpu_user_diff + os_cpu_nice_diff + os_cpu_system_diff)/(os_cpu_user_diff + os_cpu_nice_diff + os_cpu_system_diff + os_cpu_idle_diff), 1) AS os_cpu_utilization_percent,
            ROUND(os_mem_total_kb/1000, 1) AS os_mem_total_mb,
            ROUND(os_mem_free_kb/1000, 1) AS os_mem_free_mb,
            ROUND(os_mem_active_kb/1000, 1) AS os_mem_active_mb,
            ROUND((os_mem_total_kb-os_mem_free_kb)/1000, 1) AS os_mem_used_mb,
            ROUND(os_swap_total_kb/1000, 1) AS os_swap_total_mb,
            ROUND(os_swap_free_kb/1000, 1) AS os_swap_free_mb,
            ROUND((os_swap_total_kb-os_swap_free_kb)/1000, 1) AS os_swap_used_mb,

            os_root_mountpoint_usage_percent,
            os_datadir_mountpoint_usage_percent,
            os_tmpdir_mountpoint_usage_percent,
            
            os_page_ins_psec,
            os_page_outs_psec,
            os_swap_ins_psec,
            os_swap_outs_psec,
   
            %s,
            %s,
            %s
        """ % (
               ",\n".join(get_custom_status_variables()), 
               ",\n".join(get_custom_status_variables_psec()),  
               ",\n".join(get_custom_time_status_variables()),
               )
        )
    create_report_24_7_view()
    create_report_recent_views()
    create_report_sample_recent_aggregated_view()
    create_report_minmax_views()
    create_report_human_views()

    # Report chart views:
    create_report_chart_sample_timeseries_view()
    create_report_chart_hour_timeseries_view()
    create_report_chart_day_timeseries_view()
    create_report_chart_labels_views()
    report_chart_views = [
        ("uptime_percent", "uptime_percent", True, True, ["#ff8c00", ]),

        ("innodb_read_hit_percent", "innodb_read_hit_percent", False, False, ["#9acd32", ]),
        ("innodb_buffer_pool_reads_psec, innodb_buffer_pool_pages_flushed_psec", "innodb_io", True, False, ["#4682b4", "#9acd32", ]),
        ("innodb_data_files_writes_psec, innodb_log_writes_psec, innodb_dblwr_writes_psec, innodb_data_reads_psec", "innodb_rw", True, False, ["#4682b4", "#9acd32", ]),
        ("innodb_buffer_pool_used_percent, innodb_buffer_pool_pages_dirty_percent", "innodb_buffer_pool_usage", True, True, ["#dda0dd", ]),
        ("innodb_buffer_pool_pages_total, innodb_buffer_pool_pages_data, innodb_buffer_pool_pages_dirty", "innodb_buffer_pool_pages", True, False, ["#dda0dd", ]),
        ("innodb_estimated_log_mb_written_per_hour", "innodb_estimated_log_mb_written_per_hour", True, False, ["9932cc", ]),
        ("innodb_row_lock_time_psec", "innodb_row_lock_time_psec", True, False, ["808080", ]),
        ("innodb_buffer_pool_read_ahead_psec, innodb_buffer_pool_read_ahead_evicted_psec", "innodb_buffer_pool_read_ahead", True, False, ["#dda0dd", ]),

        ("mega_bytes_sent_psec, mega_bytes_received_psec", "network_io", True, False, ["#7fffd4", "808080", ]),

        ("key_buffer_used_percent", "myisam_key_buffer_used_percent", True, True, ["191970", ]),
        ("key_read_requests_psec, key_reads_psec, key_write_requests_psec, key_writes_psec", "myisam_key_hit", True, False, ["#9acd32", "#ff8c00", "#ffd700", "#4682b4", ]),

        ("com_select_psec, com_insert_psec, com_insert_select_psec, com_delete_psec, com_update_psec, com_replace_psec", "DML", True, False, ["#dc143c", "#ffd700", "#4682b4", "9acd32", "808080", ]),
        ("queries_psec, questions_psec, slow_queries_psec, com_commit_psec, com_set_option_psec", "questions", True, False, ["#7fffd4", "#ff8c00", "#4682b4", "9932cc", "ffd700", ]),
        ("innodb_rows_inserted_psec, innodb_rows_deleted_psec, innodb_rows_updated_psec", "innodb_rows", True, False, ["#dda0dd", "#7fffd4", "#4682b4", ]),

        ("created_tmp_tables_psec, created_tmp_disk_tables_psec", "tmp_tables", True, False, ["#9932cc", "#ff8c00", ]),
        ("handler_read_rnd_psec, handler_read_rnd_next_psec, handler_read_first_psec, handler_read_next_psec, handler_read_prev_psec, handler_read_key_psec", "read_patterns", True, False, ["#ff8c00", "#ffd700", "#7fffd4", "#dc143c", "9acd32", "808080" ]),

        ("table_locks_waited_psec", "table_locks_waited_psec", True, False, ["dc143c", ]),

        ("table_cache_size, open_tables, table_definition_cache_size, open_table_definitions", "table_cache_use", True, False, ["#9932cc", "7fffd4", ]),
        ("opened_tables_psec, opened_table_definitions_psec", "opened_tables_psec", True, False, ["#4682b4", "dc143c", ]),

        ("connections_psec, aborted_connects_psec, threads_created_psec", "connections", True, False, ["#ff8c00", "#dda0dd", ]),
        ("max_connections, threads_connected, threads_running", "connections_usage", True, False, ["#808080", "#ffd700", "#7fffd4", ]),

        ("thread_cache_size, threads_cached", "thread_cache_use", True, False, ["#808080", "#ff8c00", ]),
        ("threads_created_psec", "threads_created_psec", True, False, ["9932cc", ]),

        ("relay_log_space_limit_mb, relay_log_space_mb", "relay_log_used_mb", True, False, ["191970", ]),
        ("seconds_behind_main", "seconds_behind_main", True, True, ["#005E5E", "#0F006C", "#538F00", ]),
        ("seconds_behind_main_psec", "seconds_behind_main_psec", True, False, ["4682b4", ]),
        ("estimated_subordinate_catchup_seconds", "estimated_subordinate_catchup_seconds", True, False, ["9932cc", ]),

        ("os_cpu_utilization_percent", "os_cpu_utilization_percent", True, True, ["ff8c00", ]),
        ("os_loadavg, os_total_cpu_cores", "os_loadavg", True, False, ["dc143c", "7fffd4", ]),
        ("os_mem_total_mb, os_mem_used_mb, os_mem_active_mb, os_swap_total_mb, os_swap_used_mb", "os_memory", True, False, ["#7fffd4", "#191970", "#ffd700", "#4682b4", "#dc143c", ]),
        ("os_page_ins_psec, os_page_outs_psec", "os_page_io", True, False, ["#9acd32", "#ff8c00", ]),
        ("os_swap_ins_psec, os_swap_outs_psec", "os_swap_io", True, False, ["#4682b4", "#dc143c", ]),

        ("os_root_mountpoint_usage_percent, os_datadir_mountpoint_usage_percent, os_tmpdir_mountpoint_usage_percent", "os_mountpoints_usage_percent", True, True, ["#ff8c00", "#ffd700", "#4682b4", ]),
        ]
    report_chart_views.extend([
        (custom_variable, custom_variable, True, False, []) for custom_variable in get_custom_status_variables()
        ])
    report_chart_views.extend([
        (custom_variable, custom_variable, True, False, []) for custom_variable in get_custom_time_status_variables()
        ])
    report_chart_views.extend([
        (custom_variable, custom_variable, True, False, []) for custom_variable in get_custom_status_variables_psec()
        ])
    create_report_google_chart_views(report_chart_views)
    report_24_7_columns = [
        "innodb_read_hit_percent",
        "innodb_buffer_pool_reads_psec",
        "innodb_buffer_pool_pages_flushed_psec",
        "innodb_os_log_written_psec",
        "innodb_row_lock_time_psec",
        "mega_bytes_sent_psec",
        "mega_bytes_received_psec",
        "key_read_hit_percent",
        "key_write_hit_percent",
        "com_select_psec",
        "com_insert_psec",
        "com_delete_psec",
        "com_update_psec",
        "com_replace_psec",
        "com_set_option_percent",
        "com_commit_percent",
        "slow_queries_percent",
        "select_scan_psec",
        "select_full_join_psec",
        "select_range_psec",
        "table_locks_waited_psec",
        "opened_tables_psec",
        "created_tmp_tables_psec",
        "created_tmp_disk_tables_psec",
        "connections_psec",
        "aborted_connects_psec",
        "threads_created_psec",
        "seconds_behind_main",
        "os_loadavg",
        "os_cpu_utilization_percent",
        "os_mem_used_mb",
        "os_mem_active_mb",
        "os_swap_used_mb",
        ]
    create_report_google_chart_24_7_view(report_24_7_columns)

    create_custom_google_charts_views()
    create_custom_google_charts_flattened_views()
    # Report HTML views:
    create_report_html_24_7_view(report_24_7_columns)
    create_report_html_view("""
        innodb_read_hit_percent, innodb_io, innodb_rw, innodb_row_lock_time_psec, innodb_estimated_log_mb_written_per_hour, 
        innodb_buffer_pool_pages, innodb_buffer_pool_read_ahead,
        myisam_key_buffer_used_percent, myisam_key_hit,
        network_io,
        DML, questions,
        innodb_rows,
        tmp_tables,
        read_patterns,
        table_locks_waited_psec,
        table_cache_use, opened_tables_psec,
        connections, connections_usage,
        thread_cache_use, threads_created_psec,
        relay_log_used_mb, seconds_behind_main, seconds_behind_main_psec,
        uptime_percent,
        os_cpu_utilization_percent,
        os_loadavg,
        os_memory,
        os_page_io,
        os_swap_io,
        os_mountpoints_usage_percent
        """)
    brief_html_view_charts = [
            ("InnoDB & I/O", "innodb_rw, innodb_io, network_io"),
            ("InnoDB", "innodb_buffer_pool_pages, innodb_buffer_pool_read_ahead, innodb_estimated_log_mb_written_per_hour"),
            ("Questions", "DML, questions, tmp_tables"),
            ("Resources", "connections, threads_created_psec, opened_tables_psec"),
            ("Caches", "myisam_key_hit, thread_cache_use, table_cache_use"),
            ("Vitals", "seconds_behind_main, connections_usage, uptime_percent"),
            ("OS", "os_memory, os_cpu_utilization_percent, os_loadavg"),
            ("", "os_page_io, os_swap_io, os_mountpoints_usage_percent"),
        ]
    if get_custom_chart_names():
        brief_html_view_charts.append(("Custom", ", ".join(get_custom_chart_names()),))
        
    create_custom_query_top_navigation_view()
    create_report_html_brief_view(brief_html_view_charts)
    create_custom_html_view()
    create_custom_html_brief_view()


def send_email_message(description, subject, message, attachment=None):
    try:
        smtp_to = options.smtp_to
        smtp_from = options.smtp_from
        smtp_host = options.smtp_host
        
        # Create the container (outer) email message.
        msg = MIMEMultipart()
        msg["Subject"] = subject
        msg["From"] = smtp_from 
        msg["To"] = smtp_to

        message_suffix = """
    
You are receiving this email from a mycheckpoint -- MySQL monitoring utility -- installation.
Please consult your system or database administrator if you do not know why you got this mail.
-------
mycheckpoint home page: http://code.openark.org/forge/mycheckpoint
            """
        message = message + message_suffix
        msg.preamble = message
        
        if attachment:
            msg.attach(attachment)
        
        text_message = MIMEText(message)
        msg.attach(text_message)
    
        verbose("Sending %s message from %s to: %s via: %s" % (description, smtp_from, smtp_to, smtp_host))
        # Send the email via our own SMTP server.
        s = smtplib.SMTP(smtp_host)
        s.sendmail(smtp_from, smtp_to.split(","), msg.as_string())
        s.quit()
        verbose("+ Sent")
        return True
    except:
        print_error("Failed sending email")
        if options.debug:
            traceback.print_exc()
        return False
    
    
def get_html_brief_report():    
    query = "SELECT html FROM %s.sv_report_html_brief" % database_name
    brief_report = get_row(query)["html"]
    return brief_report


def email_brief_report():
    subject = "mycheckpoint brief report: %s" % database_name

    message = """Attached: mycheckpoint brief HTML report for database: %s""" % database_name
        
    brief_report = get_html_brief_report()
    
    attachment = MIMEText(brief_report, _subtype="html")
    attachment.add_header("Content-Disposition", "attachment", filename="mycheckpoint_brief_report_%s.html" % database_name)

    send_email_message("HTML brief report", subject, message, attachment)        
            

def get_html_alert_pending_report():    
    query = "SELECT html FROM %s.alert_pending_html_view" % database_name
    alert_pending_report = get_row(query, write_conn)["html"]
    return alert_pending_report


def email_alert_pending_report():
    subject = "mycheckpoint alert pending report: %s" % database_name

    message = """Attached: mycheckpoint alert pending report for database: %s""" % database_name
        
    alert_pending_report = get_html_alert_pending_report()
    
    attachment = MIMEText(alert_pending_report, _subtype="html")
    attachment.add_header("Content-Disposition", "attachment", filename="mycheckpoint_alert_pending_report_%s.html" % database_name)

    send_email_message("HTML alert pending report", subject, message, attachment)        
            
            
def email_cannot_access_database_message():
    """
    Send an email notifying that the database cannot be reached
    """
    if not options:
        return    
    if options.skip_emails:
        verbose("--skip-emails requested. Database cannot be reached; but this will not be emailed")
        return None

    email_message = """
Database alert: %s

This is an alert mail sent by mycheckpoint, monitoring your %s MySQL database.

*****************************************
mycheckpoint cannot access your database.
*****************************************
Please check:
- Is the service running?
- Are there too many connections?
- Is there a network problem?
        """ % (database_name, database_name,)
    email_subject = "%s: mycheckpoint cannot access database" % database_name
    send_email_message("cannot access", email_subject, email_message)
                                

def disable_bin_log():
    if not options.disable_bin_log:
        return
    try:
        query = "SET SESSION SQL_LOG_BIN=0"
        act_query(query)
        verbose("binary logging disabled")
    except Exception:
        exit_with_error("Failed to disable binary logging. Either grant the SUPER privilege or use --skip-disable-bin-log")


def collect_status_variables():
    global status_variables_insert_id
    global status_variables_insert_timestamp
    
    disable_bin_log()

    status_dict = fetch_status_variables()

    column_names = ", ".join(["%s" % column_name for column_name in sorted_list(status_dict.keys())])
    for column_name in status_dict.keys():
        if status_dict[column_name] is None:
            status_dict[column_name] = "NULL"
        if status_dict[column_name] == "":
            status_dict[column_name] = "NULL"
    variable_values = ", ".join(["%s" % status_dict[column_name] for column_name in sorted_list(status_dict.keys())])
    query = """INSERT /*! IGNORE */ INTO %s.%s
            (%s)
            VALUES (%s)
    """ % (database_name, table_name,
        column_names,
        variable_values)
    num_affected_rows = act_query(query)
    if num_affected_rows:
        status_variables_insert_id = get_last_insert_id()
        status_variables_insert_timestamp = get_last_written_timestamp()
        verbose("New entry added: id=%d; ts=%s" % (status_variables_insert_id, status_variables_insert_timestamp,))


def write_status_variables_hour_aggregation(aggregation_timestamp):
    if aggregation_timestamp is None:
        return
    if options.skip_aggregation:
        return
    
    global_variables, status_columns = get_variables_and_status_columns()
    
    global_variables_columns_names = ",\n".join(global_variables)
    status_columns_names = ",\n".join(status_columns)
    status_columns_diff_names = ",\n".join(["%s_diff" % (column_name,) for column_name in status_columns])

    global_variables_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in global_variables])
    status_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in status_columns])
    sum_diff_columns_listing = ",\n".join([" SUM(%s_diff) AS %s_diff" % (column_name, column_name,) for column_name in status_columns])
    query = """
        REPLACE INTO ${database_name}.status_variables_aggregated_hour 
          (
            id, 
            ts, 
            end_ts, 
            ts_diff_seconds, 
            %s, 
            %s, 
            %s
          )
          SELECT
            MIN(id) AS id,
            DATE(ts) + INTERVAL HOUR(ts) HOUR AS ts,
            DATE(ts) + INTERVAL (HOUR(ts) + 1) HOUR AS end_ts,
            SUM(ts_diff_seconds) AS ts_diff_seconds,
            %s,
            %s,
            %s
          FROM
            ${database_name}.sv_sample
          WHERE
            ts >= DATE('${aggregation_timestamp}') + INTERVAL HOUR('${aggregation_timestamp}') HOUR
            AND ts < DATE('${aggregation_timestamp}') + INTERVAL (HOUR('${aggregation_timestamp}') + 1) HOUR
          GROUP BY DATE(ts), HOUR(ts)
    """ % (status_columns_names, status_columns_diff_names, global_variables_columns_names, 
           status_columns_listing, sum_diff_columns_listing, global_variables_columns_listing)
    query = query.replace("${database_name}", database_name)
    query = query.replace("${aggregation_timestamp}", aggregation_timestamp)

    num_affected_rows = act_query(query)
    if num_affected_rows:
        verbose("%s Entry aggregated into status_variables_aggregated_hour" % aggregation_timestamp)


def write_status_variables_day_aggregation(aggregation_timestamp):
    if aggregation_timestamp is None:
        return
    if options.skip_aggregation:
        return
    
    global_variables, status_columns = get_variables_and_status_columns()
    
    global_variables_columns_names = ",\n".join(global_variables)
    status_columns_names = ",\n".join(status_columns)
    status_columns_diff_names = ",\n".join(["%s_diff" % (column_name,) for column_name in status_columns])

    global_variables_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in global_variables])
    status_columns_listing = ",\n".join([" MAX(%s) AS %s" % (column_name, column_name,) for column_name in status_columns])
    sum_diff_columns_listing = ",\n".join([" SUM(%s_diff) AS %s_diff" % (column_name, column_name,) for column_name in status_columns])
    query = """
        REPLACE INTO ${database_name}.status_variables_aggregated_day 
          (
            id, 
            ts, 
            end_ts, 
            ts_diff_seconds, 
            %s, 
            %s, 
            %s
          )
          SELECT
            MIN(id) AS id,
            DATE(ts) AS ts,
            DATE(ts) + INTERVAL 1 DAY AS end_ts,
            SUM(ts_diff_seconds) AS ts_diff_seconds,
            %s,
            %s,
            %s
          FROM
            ${database_name}.sv_sample
          WHERE
            ts >= DATE('${aggregation_timestamp}')
            AND ts < DATE('${aggregation_timestamp}') + INTERVAL 1 DAY
          GROUP BY DATE(ts)
    """ % (status_columns_names, status_columns_diff_names, global_variables_columns_names, 
           status_columns_listing, sum_diff_columns_listing, global_variables_columns_listing)
    query = query.replace("${database_name}", database_name)
    query = query.replace("${aggregation_timestamp}", aggregation_timestamp)

    num_affected_rows = act_query(query)
    if num_affected_rows:
        verbose("%s Entry aggregated into status_variables_aggregated_day" % aggregation_timestamp)


def detect_status_variables_hour_aggregation_missing_values():
    if options.skip_aggregation:
        return
    
    query = """
            SELECT 
              DISTINCT CONCAT(DATE(sv_sample.ts) + INTERVAL HOUR(sv_sample.ts) HOUR, '') AS aggregation_timestamp
            FROM 
              ${database_name}.sv_sample LEFT JOIN ${database_name}.status_variables_aggregated_hour 
                ON (DATE(sv_sample.ts) + INTERVAL HOUR(sv_sample.ts) HOUR = status_variables_aggregated_hour.ts) 
            WHERE 
              status_variables_aggregated_hour.id IS NULL
        """
    query = query.replace("${database_name}", database_name)
    rows = get_rows(query, write_conn)

    for row in rows:
        aggregation_timestamp = row["aggregation_timestamp"]
        write_status_variables_hour_aggregation(aggregation_timestamp)


def detect_status_variables_day_aggregation_missing_values():
    if options.skip_aggregation:
        return
    
    query = """
            SELECT 
              DISTINCT CONCAT(DATE(sv_sample.ts), '') AS aggregation_timestamp
            FROM 
              ${database_name}.sv_sample LEFT JOIN ${database_name}.status_variables_aggregated_day ON (DATE(sv_sample.ts) = status_variables_aggregated_day.ts) 
            WHERE 
              status_variables_aggregated_day.id IS NULL
        """
    query = query.replace("${database_name}", database_name)
    rows = get_rows(query, write_conn)

    for row in rows:
        aggregation_timestamp = row["aggregation_timestamp"]
        write_status_variables_day_aggregation(aggregation_timestamp)


def purge_status_variables():
    disable_bin_log()

    query = """DELETE FROM %s.%s WHERE ts < NOW() - INTERVAL %d DAY""" % (database_name, table_name, options.purge_days)
    num_affected_rows = act_query(query)
    if num_affected_rows:
        verbose("Old entries purged")
    return num_affected_rows


def purge_alert():
    """
    Since we support all storage engines, we define no foreign keys.
    After purging old records from status_variables, alert rows must be purged as well.
    """
    disable_bin_log()

    query = """
      DELETE 
        FROM ${database_name}.alert 
      WHERE 
        sv_report_sample_id < 
          (SELECT MIN(id) FROM ${database_name}.status_variables)"""
    query = query.replace("${database_name}", database_name)
    num_affected_rows = act_query(query)
    if num_affected_rows:
        verbose("Old alert entries purged")
    return num_affected_rows


def detect_mycheckpoint_databases(force_reload=False):
    global http_known_databases
    if http_known_databases and not force_reload:
        return
    
    try:
        monitored_connection, write_connection = open_connections()
        rows = get_rows("SHOW DATABASES", write_connection)
        known_databases = [row["Database"] for row in rows]
        mycheckpoint_databases = []
        for db in known_databases:
            try:
                row = get_row("SELECT database_name, revision, mysql_version, last_deploy FROM %s.metadata" % db , write_connection)
                mycheckpoint_databases.append(row["database_name"])
            except:
                # Not a mycheckpoint database
                pass
        print "read databases"
        http_known_databases = mycheckpoint_databases
    finally:
        if monitored_connection:
            monitored_connection.close()
        if write_connection and write_connection is not monitored_connection:
            write_connection.close()

def http_get_html_databases_list(http_database_name):
    databases_links_list = []
    for database_name in http_known_databases:
        if database_name == http_database_name:
            database_link = "<strong>%s</strong>" % database_name
        else:
            database_link = """<a href="/%s/">%s</a>""" % (database_name, database_name,)
        databases_links_list.append(database_link)
    html_databases_list = " | ".join(databases_links_list)
    return html_databases_list


def http_get_row(query):
    try:
        monitored_connection, write_connection = open_connections()
        row = get_row(query, write_connection)
        return row
    finally:
        if monitored_connection:
            monitored_connection.close()
        if write_connection and write_connection is not monitored_connection:
            write_connection.close()


def http_get_view_html(http_database_name, http_view_name):
    query = "SELECT html FROM %s.%s" % (http_database_name, http_view_name)
    row = http_get_row(query)
    html = row["html"]
    return html, query

def http_get_html_embed(http_database_name, http_view_name, html_query):
    pages_list = [
        ("sv_report_html_brief", "Brief"),
        ("sv_custom_html_brief", "Custom brief"),
        ("alert_pending_html_view", "Alert"),
        ("sv_report_html_24_7", "24/7"),
        ("sv_report_html", "Full"),
        ("sv_custom_html", "Custom full"),
        ]
    pages_links_list = []
    for (view_name, view_description) in pages_list:
        if view_name == http_view_name:
            page_link = "<strong>%s</strong>" % view_description
        else:
            page_link = """<a href="/%s/%s">%s</a>""" % (http_database_name, view_name, view_description,)
        pages_links_list.append(page_link)
        
    generating_query_text = ""
    if html_query:
        generating_query_text = "This page was generated using this query: <strong>%s</strong><br/>" % html_query

    html_embed = """
        <div class="http_html_embed">
            <a href="/">Home</a> | mycheckpoint databases [<a href="/refresh-databases-list"><i>refresh</i></a>]: %s<br/>
            Reports: %s<br/>
            %s
        </div>
        """ % (http_get_html_databases_list(http_database_name), " | ".join(pages_links_list), generating_query_text)
    return html_embed

    
def http_embed_code(html, anchor, code):
    html = html.replace(anchor, "%s%s" % (anchor, code))
    return html


def http_get_chart_zoom_html(http_database_name, chart_alias):
    """
    This HTML page is dynamically generated by the http server. There is no supporting view here.
    """
    js_queries = []
    div_queries = []
    for view_name_extension in ["sample", "hour", "day"]:
        js_query = """IFNULL(
            CONCAT('
                new openark_lchart(
                    document.getElementById("chart_div_${chart_alias}_${view_name_extension}"), 
                    {width: ${chart_width}, height: ${chart_height}, squareLines: true}
                    ).read_google_url("', sv_report_chart_${view_name_extension}.${chart_alias}_extended, '");
                '),
            '')
        """ 
        js_query = js_query.replace("${view_name_extension}", view_name_extension)
        js_queries.append(js_query)
        div_query = """'
            <div class="row">
               <div class="chart_container">
                    <div class="corner tl"></div><div class="corner tr"></div><div class="corner bl"></div><div class="corner br"></div>
                    <h3>', IFNULL(CONCAT('<a href="', sv_report_chart_${view_name_extension}.${chart_alias}, '">[url]</a>'), 'N/A'), '</h3>
                    <div id="chart_div_${chart_alias}_${view_name_extension}" class="chart"></div>
                </div>
                <div class="clear"></div>
            </div>'
            """
        div_query = div_query.replace("${view_name_extension}", view_name_extension)
        div_queries.append(div_query)

    query = """
      SELECT CONCAT('
        <html>
            <head>
            <title>', metadata.database_name, ' monitoring: full report</title>
            <!--[if IE]>
                <xml:namespace ns="urn:schemas-microsoft-com:vml" prefix="v" />
                <style> v\\\\:* { behavior: url(#default#VML); }</style >
            <![endif]-->
            <meta http-equiv="refresh" content="7200" />
            <style type="text/css">
                ', common_css, '
                div.header {
                    position: relative;
                    float: left;
                    background: #ffffff;
                    width: ', ${chart_width}+20, ';
                }
                div.row {
                }
                div.chart {
                    white-space: nowrap;
                    width: ${chart_width}px;
                }
                div.chart_container {
                    position: relative;
                    float: left;
                    white-space: nowrap;
                    padding: 10px;
                    background: #ffffff;
                    width: ${chart_width};
                    margin-right: 10px;
                    margin-bottom: 10px;
                }
            </style>
            <script type="text/javascript" charset="utf-8">
                ', openark_lchart, '
            </script>
            <script type="text/javascript" charset="utf-8">
                window.onload = function () {
            ', %s, '
                };
            </script>
            </head>
            <body>
                <a name=""></a>
                <div class="header">
                    <div class="corner bl"></div><div class="corner br"></div>
                    <div class="header_content">
                        <h1><strong class="db">', metadata.database_name, '</strong> database monitoring: ${chart_alias} zoom in</h1>
                        Report generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on <strong>',
                            DATE_FORMAT(NOW(),'%%b %%D %%Y, %%H:%%i'), '</strong>. Revision: <strong>', metadata.revision, '</strong>, build: <strong>', metadata.build, '</strong>. MySQL version: <strong>', metadata.mysql_version, '</strong>    
                        <br/>The charts on this report are generated locally and do not send data over the net. Click the <a name="none">[url]</a> links to view Google image charts.
                    </div>
                </div>
                <div class="clear"></div>
                <h2>${chart_alias}</h2>
                ',
                %s '
            </body>
        </html>
      ') AS html
      FROM
        ${database_name}.sv_report_chart_sample, 
        ${database_name}.sv_report_chart_hour, 
        ${database_name}.sv_report_chart_day, 
        ${database_name}.metadata, 
        ${database_name}.charts_api,
        ${database_name}.html_components
      """ % (",".join(js_queries), "".join(div_queries))
    query = query.replace("${database_name}", http_database_name)
    query = query.replace("${chart_alias}", chart_alias)
    query = query.replace("${chart_width}", "800")
    query = query.replace("${chart_height}", "200")
    query = query.replace("${corners_image}", corners_image.replace("'","''"))
    html = http_get_row(query)["html"]
    html_embed = http_get_html_embed(http_database_name, None, None)
    html = http_embed_code(html, '<div class="header">', html_embed)
    return html


def http_get_no_database_selected_html():
    query = """
        SELECT CONCAT('
            <html>
                <head>
                    <title>mycheckpoint monitoring server</title>
                    <meta http-equiv="refresh" content="600" />
                    <style type="text/css">
                        ', common_css, '
                        div.header {
                            position: relative;
                            background: #ffffff;
                        }
                    </style>
                </head>
                <body>
                    <a name=""></a>
                    <div class="header">
                        <div class="corner bl"></div><div class="corner br"></div>
                        <div class="header_content">
                            <h1><strong class="db">mycheckpoint monitoring server</strong>: no database selected</h1>
                            Page generated by <a href="http://code.openark.org/forge/mycheckpoint" target="mycheckpoint">mycheckpoint</a> on <strong>',
                                DATE_FORMAT(NOW(),'%%b %%D %%Y, %%H:%%i'), '</strong>. Revision: <strong>', metadata.revision, '</strong>, build: <strong>', metadata.build, '</strong>. MySQL version: <strong>', metadata.mysql_version, '</strong>    
                            <br/>The mycheckpoint monitoring server is an HTTP interface to your mycheckpoint monitoring databases. 
                            Be advised that the charts and HTML pages are dynamically generated via SQL queries from the relevant views;
                            this server merely tunnels them through. It will present you with the originating query on each report page.
                            <br/><br/>You do not have to use the mycheckpoint monitoring server is order to view the HTML reports. In fact, you do not
                            have to use any server. The HTML reports are self contained, including JavaScript charting code, and can be viewed even
                            as local files.
                            <hr/>
                            Select database: [<a href="/refresh-databases-list"><i>refresh</i></a>] %s
                        </div>
                    </div>
                    <div class="clear"></div>
                </body>
            </html>
          ') AS html
          FROM
            ${database_name}.metadata, 
            ${database_name}.charts_api,
            ${database_name}.html_components
        """ % (http_get_html_databases_list(""))
    query = query.replace("${database_name}", database_name)
    html = http_get_row(query)["html"]
    return html


class MCPHttpHandler(BaseHTTPRequestHandler):
    def serve_content(self, content):
        content = content.replace("<!--mcp_http", "")
        content = content.replace("mcp_http-->", "")
        self.send_response(200)
        self.send_header("Content-type", "text/html")
        self.end_headers()
        self.wfile.write(content)
        
    def do_GET(self):
        try:
            database_match = re.match("^/([^/]+)[/]?$", self.path)
            database_view_match = re.match("^/([^/]+)/([^/]+)[/]?$", self.path)
            chart_zoom_match = re.match("^/([^/]+)/zoom/([^/]+)[/]?$", self.path)
            http_view_name = None
            if database_match:
                http_database_name = database_match.group(1)
                http_view_name = "sv_report_html_brief"
            elif database_view_match:
                http_database_name = database_view_match.group(1)
                http_view_name = database_view_match.group(2)
            elif chart_zoom_match:
                http_database_name = chart_zoom_match.group(1)
                
            html = None
            if self.path == "/refresh-databases-list":
                detect_mycheckpoint_databases(True)
                
            if database_match or database_view_match:
                if http_database_name in http_known_databases:
                    html, html_query = http_get_view_html(http_database_name, http_view_name)
                    html_embed = http_get_html_embed(http_database_name, http_view_name, html_query)
                    html = http_embed_code(html, '<div class="header">', html_embed)
            elif chart_zoom_match:
                chart_alias = chart_zoom_match.group(2)
                html = http_get_chart_zoom_html(http_database_name, chart_alias)

            if not html:
                html = http_get_no_database_selected_html()
            # html must be applied at this point
            self.serve_content(html)
        except IOError:
            self.send_error(404, "Page Not Found: %s" % self.path)
     

def serve_http():
    if options.run_as_service and not options.allow_http_as_service:
        verbose("Running as a service, but --allow_http_as_service not provided. Skipping HTTP")
        return
    
    try:
        detect_mycheckpoint_databases()
        http_server = HTTPServer(('', options.http_port), MCPHttpHandler)
        print "started httpserver on port %d..." % options.http_port
        http_server.serve_forever()
    except KeyboardInterrupt:
        print "SIGTERM/^C received, shutting down server"
        http_server.socket.close()
    

def deploy_schema():
    create_metadata_table()
    create_numbers_table()
    create_charts_api_table()
    create_html_components_table()
    create_custom_query_table()
    create_custom_query_view()
    if not create_status_variables_table():
        upgrade_status_variables_table()
    create_alert_condition_table()
    create_alert_table()
    create_alert_pending_table()
    create_status_variables_views_and_aggregations()
    # Some of the following depend on sv_report_chart_sample
    create_alert_view()
    create_alert_pending_view()
    create_alert_pending_html_view()
    create_alert_email_message_items_view()
    create_alert_condition_query_view()
    finalize_deploy()
    verbose("Table and views deployed")


def verify_single_instance():
    global fh
    fh = open(os.path.realpath(__file__), 'r')
    try:
        fcntl.flock(fh,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except:
        exit_with_error("lock found, process already running, exit")
    else:
        pass    


def exit_with_error(error_message):
    """
    Notify and exit.
    """
    print_error(error_message)
    sys.exit(1)


try:
    try:
        # The following are overwritten by the ANT build script, and indicate
        # the revision number (e.g. SVN) and build number (e.g. timestamp)
        # In case ANT does not work for some reason, both are assumed to be 0.
        revision_placeholder = "revision.placeholder"
        if not revision_placeholder.isdigit():
            revision_placeholder = "0"
        revision_number = int(revision_placeholder)
        build_placeholder = "build.placeholder"
        if not build_placeholder.isdigit():
            build_placeholder = "0"
        build_number = int(build_placeholder)

        monitored_conn = None
        write_conn = None
        options = None
        args = None
        parse_options()

        verbose("mycheckpoint rev %d, build %d. Copyright (c) 2009-2013 by Shlomi Noach" % (revision_number, build_number), options.version)
        
        warnings.simplefilter("ignore", MySQLdb.Warning) 
        database_name = options.database
        table_name = "status_variables"
        status_dict = {}
        extra_dict = {}
        report_columns = []
        custom_query_ids = None
        custom_query_ids_charts_enabled = None
        custom_chart_names = None
        http_known_databases = []
        status_variables_insert_id = None
        status_variables_insert_timestamp = None
        options.chart_width = max(options.chart_width, 150)
        options.chart_height = max(options.chart_height, 100)
        http_server = None

        if options.single:
            verify_single_instance()

        # Sanity:
        if not database_name:
            exit_with_error("No database specified. Specify with -d or --database")
        if options.purge_days < 1:
            exit_with_error("purge-days must be at least 1")
        verbose("database is %s" % database_name)
        
        # Read arguments
        should_deploy = False
        should_email_brief_report = False
        should_email_alert_pending_report = False
        should_serve_http = False
        for arg in args:
            if arg == "deploy":
                verbose("Deploy requested. Will deploy")
                should_deploy = True
            elif arg == "email_brief_report":
                should_email_brief_report = True
            elif arg == "email_alert_pending_report":
                should_email_alert_pending_report = True
            elif arg == "http":
                should_serve_http = True
            else:
                exit_with_error("Unknown command: %s" % arg)

        # Open connections. From this point and on, database access is possible
        monitored_conn, write_conn = open_connections()
        init_connections()

        if not should_deploy:
            if not should_serve_http and not is_same_deploy():
                verbose("Non matching deployed revision. Will auto-deploy")
                should_deploy = True

        if should_deploy:
            deploy_schema()
            detect_status_variables_hour_aggregation_missing_values()
            detect_status_variables_day_aggregation_missing_values()
            should_deploy = False
            
        # Only take record if no arguments provided (no "command")
        if not args:
            collect_status_variables()
            if purge_status_variables():
                purge_alert()
            collect_custom_data()
            write_status_variables_hour_aggregation(status_variables_insert_timestamp)
            write_status_variables_day_aggregation(status_variables_insert_timestamp)
            check_alerts()
            verbose("Status variables checkpoint complete")
            
        else:
            verbose("Will not monitor the database")
            
        if should_email_brief_report:
            email_brief_report()
            
        if should_email_alert_pending_report:
            email_alert_pending_report()
            
        if should_serve_http:
            serve_http()
            
    except Exception, err:
        if not monitored_conn:
            print_error("Cannot connect to database")
            email_cannot_access_database_message()
        print err
        if options.debug:
            traceback.print_exc()

        if "deploy" in args:
            prompt_deploy_instructions()
        else:
            prompt_collect_instructions()

        sys.exit(1)

finally:
    if monitored_conn:
        monitored_conn.close()
    if write_conn and write_conn is not monitored_conn:
        write_conn.close()
