# -*- coding: utf-8 -*-
"""IPTV Simple Module"""

from __future__ import absolute_import, division, unicode_literals

import logging
import os
import time

import dateutil.parser
import dateutil.tz

from resources.lib import kodiutils

_LOGGER = logging.getLogger(__name__)

IPTV_SIMPLE_ID = 'pvr.iptvsimple'
IPTV_SIMPLE_PLAYLIST = 'playlist.m3u8'
IPTV_SIMPLE_EPG = 'epg.xml'


class IptvSimple:
    """Helper class to setup IPTV Simple"""

    restart_required = False

    def __init__(self):
        """Init"""

    @classmethod
    def setup(cls):
        """Setup IPTV Simple"""
        try:
            # Install IPTV Simple
            kodiutils.execute_builtin('InstallAddon', IPTV_SIMPLE_ID)

            # Activate IPTV Simple so we can get the addon to be able to configure it
            cls._activate()
            addon = kodiutils.get_addon(IPTV_SIMPLE_ID)
        except Exception as exc:  # pylint: disable=broad-except
            _LOGGER.warning('Could not setup IPTV Simple: %s', str(exc))
            return False

        # Deactivate IPTV Simple to hide the "Needs to be restarted" messages
        cls._deactivate()

        # Configure IPTV Simple
        output_dir = kodiutils.addon_profile()

        addon.setSetting('m3uPathType', '0')  # Local path
        addon.setSetting('m3uPath', os.path.join(output_dir, IPTV_SIMPLE_PLAYLIST))

        addon.setSetting('epgPathType', '0')  # Local path
        addon.setSetting('epgPath', os.path.join(output_dir, IPTV_SIMPLE_EPG))
        addon.setSetting('epgCache', 'true')
        addon.setSetting('epgTimeShift', '0')

        addon.setSetting('logoPathType', '0')  # Local path
        addon.setSetting('logoPath', '/')

        addon.setSetting('catchupEnabled', 'true')
        addon.setSetting('allChannelsCatchupMode', '1')
        addon.setSetting('catchupOnlyOnFinishedProgrammes', 'false')

        # Activate IPTV Simple
        cls._activate()

        return True

    @classmethod
    def restart(cls, force=False):
        """Restart IPTV Simple"""
        if not force and (kodiutils.get_cond_visibility('Pvr.IsPlayingTv') or kodiutils.get_cond_visibility('Pvr.IsPlayingRadio')):
            # Don't restart when we are Playing TV or Radio
            cls.restart_required = True
            _LOGGER.info('Postponing restart of Simple IPTV since it is currently in use.')
            return

        cls.restart_required = False

        cls._deactivate()
        time.sleep(1)
        cls._activate()

    @staticmethod
    def _activate():
        """Activate IPTV Simple"""
        kodiutils.jsonrpc(method="Addons.SetAddonEnabled", params={"addonid": IPTV_SIMPLE_ID, "enabled": True})

    @staticmethod
    def _deactivate():
        """Deactivate IPTV Simple"""
        kodiutils.jsonrpc(method="Addons.SetAddonEnabled", params={"addonid": IPTV_SIMPLE_ID, "enabled": False})

    @staticmethod
    def write_playlist(channels):
        """Write playlist data"""
        output_dir = kodiutils.addon_profile()

        # Make sure our output dir exists
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        # Write playlist for IPTV Simple
        playlist_path = os.path.join(output_dir, IPTV_SIMPLE_PLAYLIST)

        with open(playlist_path + '.tmp', 'wb') as fdesc:
            m3u8_data = '#EXTM3U\n'

            for addon in channels:
                m3u8_data += '## {addon_name}\n'.format(**addon)
                for channel in addon['channels']:
                    m3u8_data += '#EXTINF:-1 tvg-name="{name}"'.format(**channel)
                    if channel.get('id'):
                        m3u8_data += ' tvg-id="{id}"'.format(**channel)
                    if channel.get('logo'):
                        m3u8_data += ' tvg-logo="{logo}"'.format(**channel)
                    if channel.get('preset'):
                        m3u8_data += ' tvg-chno="{preset}"'.format(**channel)
                    if channel.get('group'):
                        m3u8_data += ' group-title="{group}"'.format(**channel)
                    if channel.get('radio'):
                        m3u8_data += ' radio="true"'
                    if channel.get('vod'):
                        m3u8_data += ' catchup="vod"'

                    m3u8_data += ',{name}\n{stream}\n\n'.format(**channel)

            fdesc.write(m3u8_data.encode('utf-8'))

        # Move new file to the right place
        if os.path.isfile(playlist_path):
            os.remove(playlist_path)

        os.rename(playlist_path + '.tmp', playlist_path)

    @classmethod
    def write_epg(cls, epg):
        """Write EPG data"""
        output_dir = kodiutils.addon_profile()

        # Make sure our output dir exists
        if not os.path.exists(output_dir):
            os.mkdir(output_dir)

        epg_path = os.path.join(output_dir, IPTV_SIMPLE_EPG)

        # Write XML file by hand
        # The reason for this is that it takes less memory to write the file line by line then to construct an
        # XML object in memory and writing that in one go.
        # We can't depend on lxml.etree.xmlfile, since that's not available as a Kodi module
        with open(epg_path + '.tmp', 'wb') as fdesc:
            fdesc.write('<?xml version="1.0" encoding="UTF-8"?>\n'.encode('utf-8'))
            fdesc.write('<!DOCTYPE tv SYSTEM "xmltv.dtd">\n'.encode('utf-8'))
            fdesc.write('<tv>\n'.encode('utf-8'))

            # Write channel info
            for _, key in enumerate(epg):
                fdesc.write('<channel id="{key}"></channel>\n'.format(key=cls._xml_encode(key)).encode('utf-8'))

            # Write program info
            for _, key in enumerate(epg):
                for item in epg[key]:
                    start = dateutil.parser.parse(item.get('start')).strftime('%Y%m%d%H%M%S %z')
                    stop = dateutil.parser.parse(item.get('stop')).strftime('%Y%m%d%H%M%S %z')
                    title = item.get('title')

                    # Add an icon ourselves in Kodi 18
                    if title and item.get('stream') and kodiutils.kodi_version_major() < 19:
                        # We use a clever way to hide the direct URI in the label so Kodi 18 can access the it
                        title = '%s [COLOR green]•[/COLOR][COLOR vod="%s"][/COLOR]' % (
                            title, item.get('stream')
                        )

                    program = '<programme start="{start}" stop="{stop}" channel="{channel}"{vod}>\n'.format(
                        start=start,
                        stop=stop,
                        channel=cls._xml_encode(key),
                        vod=' catchup-id="%s"' % cls._xml_encode(item.get('stream')) if item.get('stream') else '')

                    program += ' <title>{title}</title>\n'.format(
                        title=cls._xml_encode(title))

                    if item.get('description'):
                        program += ' <desc>{description}</desc>\n'.format(
                            description=cls._xml_encode(item.get('description')))

                    if item.get('subtitle'):
                        program += ' <sub-title>{subtitle}</sub-title>\n'.format(
                            subtitle=cls._xml_encode(item.get('subtitle')))

                    if item.get('episode'):
                        program += ' <episode-num system="onscreen">{episode}</episode-num>\n'.format(
                            episode=cls._xml_encode(item.get('episode')))

                    if item.get('image'):
                        program += ' <icon src="{image}"/>\n'.format(
                            image=cls._xml_encode(item.get('image')))

                    if item.get('date'):
                        program += ' <date>{date}</date>\n'.format(
                            date=cls._xml_encode(item.get('date')))

                    if item.get('genre'):
                        program += ' <category>{genre}</category>\n'.format(
                            genre=cls._xml_encode(item.get('genre')))

                    program += '</programme>\n'

                    fdesc.write(program.encode('utf-8'))

            fdesc.write('</tv>\n'.encode('utf-8'))

        # Move new file to the right place
        if os.path.isfile(epg_path):
            os.remove(epg_path)

        os.rename(epg_path + '.tmp', epg_path)

    @staticmethod
    def _xml_encode(value):
        """Quick and dirty encoding for XML values"""
        if value is None:
            return ''
        return value \
            .replace('&', '&amp;') \
            .replace('<', '&lt;') \
            .replace('>', '&gt;') \
            .replace('"', '&quot;')
