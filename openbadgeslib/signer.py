#!/usr/bin/env python3
"""
        OpenBadges Library

        Copyright (c) 2014, Luis González Fernández, luisgf@luisgf.es
        Copyright (c) 2014, Jesús Cea Avión, jcea@jcea.es

        All rights reserved.

        This library is free software; you can redistribute it and/or
        modify it under the terms of the GNU Lesser General Public
        License as published by the Free Software Foundation; either
        version 3.0 of the License, or (at your option) any later version.

        This library is distributed in the hope that it will be useful,
        but WITHOUT ANY WARRANTY; without even the implied warranty of
        MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
        Lesser General Public License for more details.

        You should have received a copy of the GNU Lesser General Public
        License along with this library.
"""

import logging
logger = logging.getLogger(__name__)

import os
import sys
import time
import json

from datetime import datetime
from xml.dom.minidom import parse, parseString

from .errors import UnknownKeyType, FileToSignNotExists, BadgeSignedFileExists, ErrorSigningFile, PrivateKeyReadError

from .util import sha1_string, sha256_string
from .keys import KeyFactory
from .verifier import VerifyFactory

from .jws import utils as jws_utils
from .jws import sign as jws_sign

def SignerFactory(key_type='RSA'):
    """ Signer Factory Object, Return a Given object type passing a name
        to the constructor. """

    if key_type == 'ECC':
        return SignerECC()
    if key_type == 'RSA':
        return SignerRSA()
    else:
        raise UnknownKeyType()

class SignerBase():
    """ JWS Signer Factory """

    def __init__(self, issuer='', badge_name='', badge_file_path=None, badge_image_url=None, badge_json_url=None, receptor='', evidence=None, verify_key_url=None, debug_enabled=False):
        self._issuer = issuer.encode('utf-8')
        self._badge_name = badge_name.encode('utf-8')
        self._badge_file_path = badge_file_path         # Path to loca file
        self._badge_image_url = badge_image_url
        self._badge_json_url = badge_json_url
        self._receptor = receptor.encode('utf-8')      # Receptor of the badge
        self._evidence = evidence                      # Url to the user evidence
        self._verify_key_url = verify_key_url
        self.in_debug = debug_enabled                 # Debug mode enabledl

    def generate_uid(self):
        return sha1_string(self._issuer + self._badge_name + self._receptor + datetime.now().isoformat().encode('utf-8'))

    def generate_jws_payload(self):

        # All this data MUST be a Str string in order to be converted to json properly.
        recipient_data = dict (
            identity = (b'sha256$' + sha256_string(self._receptor)).decode('utf-8'),
            type = 'email',
            hashed = 'true'
        )

        verify_data = dict(
            type = 'signed',
            url = self._verify_key_url
        )

        payload = dict(
                        uid = self.generate_uid().decode('utf-8'),
                        recipient = recipient_data,
                        image = self._badge_image_url,
                        badge = self._badge_json_url,
                        verify = verify_data,
                        issuedOn = int(time.time())
                     )

        if self._evidence:
            payload['evidence'] = self._evidence

        self.debug('JWS Payload %s ' % json.dumps(payload))

        return payload

    def sign_svg(self, svg_in, assertion):
        svg_doc = parseString(svg_in)

        # Assertion
        xml_tag = svg_doc.createElement("openbadges:assertion")
        xml_tag.attributes['xmlns:openbadges'] = 'http://openbadges.org'
        svg_doc.childNodes[1].appendChild(xml_tag)
        xml_tag.attributes['verify']= assertion.decode('utf-8')
        svg_doc.childNodes[1].appendChild(xml_tag)

        """ Log the signing process before returning it.
                That's prevents the existence of a signed badge without traces """

        logger.info('"%s" SIGNED successfully for receptor "%s"' % (self._badge_name, self._receptor.decode('utf-8')))

        svg_signed = svg_doc.toxml(encoding='UTF-8')  # In Upper Case!
        svg_doc.unlink()

        return svg_signed

    def debug(self, msg):
        """ Show debug messages if debug mode is enabled """

        if self.in_debug:
            print('DEBUG:', msg)

    def generate_output_filename(self, file_in, output_dir, receptor):
        """ Generate an output filename based on the source
            name and the receptor email """

        fbase = os.path.basename(file_in)
        fname, fext = os.path.splitext(fbase)
        fsuffix = receptor.replace('@','_').replace('.','_')

        return output_dir + fname + '_'+ fsuffix + fext

    def generate_openbadge_assertion(self, priv_key_pem, pub_key_pem):
        """ Generate and Sign and OpenBadge assertion """

        header = self.generate_jose_header()
        payload = self.generate_jws_payload()

        self.key.read_private_key(priv_key_pem)
        self.key.read_public_key(pub_key_pem)

        signature = jws_sign(header, payload, self.key.get_priv_key())
        assertion = jws_utils.encode(header) + b'.' + jws_utils.encode(payload) + b'.' + jws_utils.to_base64(signature)

        """
        Code deactivated until config.ini refactorizacion of VerifyFactory()

        # Verify the assertion just after the generation.
        vf = VerifyFactory(self.conf)
        vf.load_pubkey_inline(kf.get_pub_key_pem())

        if not vf.verify_jws_signature(assertion, self.key.get_pub_key()):
            return None
        else:
            self.debug('Assertion %s' % assertion)
            return assertion
        """
        return assertion

class SignerRSA(SignerBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.key = KeyFactory('RSA')

    def generate_jose_header(self):
        jose_header = { 'alg': 'RS256' }

        self.debug('JOSE HEADER %s ' % json.dumps(jose_header))
        return jose_header

class SignerECC(SignerBase):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.key = KeyFactory('ECC')

    def generate_jose_header(self):
        jose_header = { 'alg': 'ES256' }

        self.debug('JOSE HEADER %s ' % json.dumps(jose_header))
        return jose_header


