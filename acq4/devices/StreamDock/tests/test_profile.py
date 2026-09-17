"""Tests for Stream Dock profile generation and reconciliation.

Everything here runs against a temporary profile tree and a temporary
``StreamDockConfig.ini``; no Stream Dock hardware, no VSD Craft and no Qt are involved.
The two process-control calls that reconciliation makes -- "is VSD Craft running" and
"start it" -- are stubbed out, since a test must neither kill nor launch the real thing.
"""

from __future__ import annotations

import json

import pytest

from acq4.devices.StreamDock import profile

DEVICE = 'VSDN4Pro'

#: VSD Craft's built-in page-switch action. acq4 never places one -- where it goes is the
#: user's choice in VSD Craft -- so it only ever appears here as user-placed content.
PAGE_CHANGE_UUID = 'com.hotspot.streamdock.page.change'


# --------------------------------------------------------------------------- fixtures


def writeIni(root, profileDir):
    """Write a StreamDockConfig.ini pointing at *profileDir*."""
    ini = root / 'config' / 'StreamDockConfig.ini'
    ini.parent.mkdir(parents=True, exist_ok=True)
    ini.write_text(
        '[StreamDockCurrentDevice]\n'
        f'Device={DEVICE}\n'
        '\n'
        f'[{DEVICE}DeviceConfig]\n'
        f'DeviceUUID={DEVICE}\n'
        f'sdProfilePath="{str(profileDir).replace(chr(92), chr(92) * 2)}"\n',
        encoding='utf-8',
    )
    return ini


def handBuiltEntry(name='Hand built'):
    """An action a user placed themselves: no generator tag, so it must never be touched."""
    return {
        'ActionID': 'hand-built-action-id',
        'Controller': '',
        'Name': name,
        'Settings': {},
        'State': 0,
        'States': [{'Image': 'images/x.png', 'Title': name}],
        'UUID': 'com.example.someones.plugin.thing',
    }


def pageChangeEntry():
    """A page-change action as VSD Craft writes it: untagged, so it is the user's."""
    return {
        'ActionID': 'user-placed-page-change',
        'Controller': '',
        'Name': 'change page',
        'Settings': {},
        'State': 0,
        'States': [{'Image': ''}],
        'UUID': PAGE_CHANGE_UUID,
    }


def strayEntry():
    """The oddity the rig's live parent manifest carries.

    An untagged ``com.acq4.streamdock.button`` at panel position ``-1,-1`` with empty
    ``Settings``. It has no generator tag, so nothing may treat it as ours.
    """
    return {
        'ActionID': 'stray-action-id',
        'Controller': '',
        'Name': 'ACQ4 Button',
        'Settings': {},
        'State': 0,
        'States': [{'Image': 'images/button.png', 'Title': ''}],
        'UUID': f'{profile.PLUGIN_UUID}.button',
    }


@pytest.fixture
def profileTree(tmp_path, monkeypatch):
    """A profile directory holding one hand-built page, wired up as the current device.

    Returns the profile directory. The parent manifest *is* the profile's first page, which
    is why reconciliation never generates it. It carries no page-change key, matching the
    rig's live profile, plus the stray untagged key that profile also has.
    """
    profileDir = tmp_path / 'profiles' / 'PARENT01.sdProfile'
    profileDir.mkdir(parents=True)
    (profileDir / 'Images').mkdir()
    profile.write_json(
        profileDir / 'manifest.json',
        {
            'Actions': {
                '0,1': handBuiltEntry(),
                '-1,-1': strayEntry(),
            },
            'DeviceModel': '20GBA9901',
            'DeviceSerialNumber': '01E2D2782A19',
            'DeviceUUID': DEVICE,
            'Name': 'Scenes 1',
            'Pages': {'Current': profileDir.name, 'Pages': [profileDir.name]},
            'Version': '1.0',
        },
    )
    writeIni(tmp_path, profileDir)
    monkeypatch.setattr(profile, 'CONFIG_INI', tmp_path / 'config' / 'StreamDockConfig.ini')
    monkeypatch.setattr(profile, 'vsd_craft_running', lambda: False)
    monkeypatch.setattr(profile, 'launch_vsd_craft', lambda: None)
    monkeypatch.setattr(profile, 'stop_vsd_craft', lambda timeout=20.0: True)
    return profileDir


@pytest.fixture
def spec():
    """A VSD N4 Pro layout: ten keys in two rows, three knobs on the strip below them."""
    return profile.GridSpec(button_rows=2, button_cols=5, dial_rows=1, dial_cols=3)


def readPage(profileDir, folder):
    return profile.read_json(profileDir / 'profiles' / folder / 'manifest.json')


def generatedSettings(manifest):
    """``{panel key: Settings}`` for the generated keys of one page."""
    return {
        key: entry['Settings']
        for key, entry in manifest['Actions'].items()
        if (entry.get('Settings') or {}).get('generator') == profile.GENERATOR_TAG
    }


# ---------------------------------------------------------------------------- geometry


class TestGridSpec:
    def test_block_addresses_are_per_block(self, spec):
        assert spec.shape('button') == (2, 5)
        assert spec.shape('dial') == (1, 3)
        assert spec.keys('dial') == [(0, 0), (0, 1), (0, 2)]
        assert len(spec.keys('button')) == 10

    def test_dials_occupy_the_bottom_rows_and_buttons_sit_above(self, spec):
        # panel rows count up from the bottom: the knob strip is row 0, and block row 0 is
        # the *top* row of its block, so the first button is panel row 2
        assert spec.panelPosition('dial', 0, 0) == (0, 0)
        assert spec.panelPosition('dial', 0, 2) == (2, 0)
        assert spec.panelPosition('button', 0, 0) == (0, 2)
        assert spec.panelPosition('button', 1, 4) == (4, 1)

    def test_panel_placement_of_the_rig_layout(self, spec):
        """Pin every panel position of the rig's 2x5 buttons + 1x4 dials.

        Physically, top to bottom: button row 0, button row 1, then the knobs. Panel row 0
        is the knob strip at the bottom, so the panel row index runs the other way.
        """
        rig = profile.GridSpec(button_rows=2, button_cols=5, dial_rows=1, dial_cols=4)
        assert profile.spec_layout(rig) == {
            # top button row
            '0,2': ('button', 0, 0),
            '1,2': ('button', 0, 1),
            '2,2': ('button', 0, 2),
            '3,2': ('button', 0, 3),
            '4,2': ('button', 0, 4),
            # bottom button row
            '0,1': ('button', 1, 0),
            '1,1': ('button', 1, 1),
            '2,1': ('button', 1, 2),
            '3,1': ('button', 1, 3),
            '4,1': ('button', 1, 4),
            # the knob strip, panel row 0
            '0,0': ('dial', 0, 0),
            '1,0': ('dial', 0, 1),
            '2,0': ('dial', 0, 2),
            '3,0': ('dial', 0, 3),
        }
        # 14 of the panel's 15 keys; 4,0 -- the fifth knob slot -- is the one left free,
        # and nothing about it is reserved: acq4 places no page-change key anywhere
        assert '4,0' not in profile.spec_layout(rig)
        assert rig.panelPosition('dial', 0, 3) == (3, 0)

    def test_panel_extent(self, spec):
        assert (spec.rows, spec.columns) == (3, 5)

    def test_out_of_block_address_raises(self, spec):
        with pytest.raises(ValueError):
            spec.panelPosition('button', 2, 0)
        with pytest.raises(ValueError):
            spec.panelPosition('trackball', 0, 0)

    def test_geometry_is_checked_against_the_reported_panel(self, tmp_path, spec):
        meta = tmp_path / 'ws-meta.json'
        meta.write_text(
            json.dumps(
                {'info': {'devices': [{'name': DEVICE, 'size': {'columns': 5, 'rows': 3}}]}}
            ),
            encoding='utf-8',
        )
        profile.check_geometry(spec, DEVICE, meta)  # fits exactly

        tooTall = profile.GridSpec(button_rows=3, button_cols=5, dial_rows=1, dial_cols=3)
        with pytest.raises(profile.ProfileError, match='is 3x5'):
            profile.check_geometry(tooTall, DEVICE, meta)

        tooWide = profile.GridSpec(button_rows=2, button_cols=6, dial_rows=1, dial_cols=3)
        with pytest.raises(profile.ProfileError):
            profile.check_geometry(tooWide, DEVICE, meta)

    def test_geometry_check_is_skipped_without_a_reported_size(self, tmp_path, spec):
        # nothing to check against before the plugin has ever run; must not raise
        profile.check_geometry(spec, DEVICE, tmp_path / 'absent.json')

    def test_device_size_reads_the_info_payload(self, tmp_path):
        meta = tmp_path / 'ws-meta.json'
        meta.write_text(
            json.dumps(
                {
                    'info': {
                        'devices': [
                            {'name': 'VSDN3', 'size': {'columns': 4, 'rows': 3}},
                            {'name': DEVICE, 'size': {'columns': 5, 'rows': 3}},
                        ]
                    }
                }
            ),
            encoding='utf-8',
        )
        assert profile.device_size(DEVICE, meta) == (5, 3)
        assert profile.device_size('VSDN3', meta) == (4, 3)
        assert profile.device_size('VSDM18', meta) is None


# ----------------------------------------------------------------------- device lookup


class TestFindDeviceProfile:
    def test_resolves_the_current_device(self, profileTree):
        found, device = profile.find_device_profile()
        assert found == profileTree
        assert device == DEVICE

    def test_named_device(self, profileTree):
        assert profile.find_device_profile(DEVICE)[0] == profileTree

    def test_unknown_device_raises(self, profileTree):
        with pytest.raises(profile.ProfileError, match='VSDN3'):
            profile.find_device_profile('VSDN3')


# --------------------------------------------------------------------- reconciliation


class TestEnsurePages:
    def test_generates_pages_from_none(self, profileTree, spec):
        result = profile.ensure_pages(3, spec=spec)
        assert result['changed'] is True
        assert (result['have'], result['want']) == (0, 3)
        assert len(result['added']) == 3
        assert result['removed'] == []

        parent = profile.read_json(profileTree / 'manifest.json')
        # the parent page plus three generated ones
        assert len(parent['Pages']['Pages']) == 4
        assert parent['Pages']['Pages'][0] == profileTree.name
        for folder in result['pages']:
            assert (profileTree / 'profiles' / folder / 'manifest.json').exists()
            assert (profileTree / 'profiles' / folder / 'Images').is_dir()

    def test_generated_keys_carry_the_logical_block_address(self, profileTree, spec):
        result = profile.ensure_pages(1, spec=spec)
        settings = generatedSettings(readPage(profileTree, result['pages'][0]))

        # dials on panel row 0, addressed (0, 0..2) within their own block
        assert settings['0,0']['role'] == 'dial'
        assert (settings['0,0']['row'], settings['0,0']['column']) == (0, 0)
        # button (0, 0) is panel row 2 -- the address is per block, not per panel
        assert settings['0,2']['role'] == 'button'
        assert (settings['0,2']['row'], settings['0,2']['column']) == (0, 0)
        assert (settings['4,1']['row'], settings['4,1']['column']) == (1, 4)
        assert len(settings) == 13  # 3 dials + 10 buttons

    def test_page_identity_is_baked_in(self, profileTree, spec):
        result = profile.ensure_pages(2, spec=spec, label='rig')
        for index, folder in enumerate(result['pages']):
            for settings in generatedSettings(readPage(profileTree, folder)).values():
                assert settings['generator'] == 'acq4'
                assert settings['pageId'] == folder.removesuffix('.sdProfile')
                assert settings['pageIndex'] == index
                assert settings['pageLabel'] == f'rig {index + 1}'

    def test_adds_pages_to_reach_the_requested_count(self, profileTree, spec):
        first = profile.ensure_pages(1, spec=spec)['pages']
        result = profile.ensure_pages(3, spec=spec)
        assert (result['have'], len(result['added']), result['removed']) == (1, 2, [])
        # the page that was already there keeps its identity
        assert result['pages'][0] == first[0]

    def test_removes_pages_to_reach_the_requested_count(self, profileTree, spec):
        before = profile.ensure_pages(4, spec=spec)['pages']
        result = profile.ensure_pages(2, spec=spec)
        assert (result['have'], len(result['removed'])) == (4, 2)
        assert result['pages'] == before[:2]
        for folder in result['removed']:
            assert not (profileTree / 'profiles' / folder).exists()
        parent = profile.read_json(profileTree / 'manifest.json')
        for folder in result['removed']:
            assert folder not in parent['Pages']['Pages']

    def test_nothing_to_do_is_a_no_op(self, profileTree, spec):
        profile.ensure_pages(2, spec=spec)
        mtime = (profileTree / 'manifest.json').stat().st_mtime_ns
        result = profile.ensure_pages(2, spec=spec)
        assert result['changed'] is False
        assert result['added'] == result['removed'] == result['rewritten'] == []
        assert (profileTree / 'manifest.json').stat().st_mtime_ns == mtime

    def test_zero_pages_removes_everything_generated(self, profileTree, spec):
        profile.ensure_pages(2, spec=spec)
        result = profile.ensure_pages(0, spec=spec)
        assert result['pages'] == []
        assert len(result['removed']) == 2
        parent = profile.read_json(profileTree / 'manifest.json')
        assert parent['Pages']['Pages'] == [profileTree.name]

    def test_negative_page_count_raises(self, profileTree, spec):
        with pytest.raises(ValueError):
            profile.ensure_pages(-1, spec=spec)


class TestHandBuiltPagesSurvive:
    def test_the_parent_page_is_never_generated_or_touched(self, profileTree, spec):
        before = profile.read_json(profileTree / 'manifest.json')['Actions']
        profile.ensure_pages(2, spec=spec)
        after = profile.read_json(profileTree / 'manifest.json')['Actions']
        assert after == before

    def test_a_hand_built_child_page_is_left_alone(self, profileTree, spec):
        parent = profile.read_json(profileTree / 'manifest.json')
        mine = 'MANUAL01.sdProfile'
        parent['Pages']['Pages'].append(mine)
        profile.write_json(profileTree / 'manifest.json', parent)
        manual = {
            'Actions': {'0,0': handBuiltEntry('Mine')},
            'DeviceUUID': DEVICE,
            'Name': 'Mine',
            'Version': '1.0',
        }
        profile.write_json(profileTree / 'profiles' / mine / 'manifest.json', manual)

        result = profile.ensure_pages(2, spec=spec)
        assert mine not in result['pages']
        assert profile.read_json(profileTree / 'profiles' / mine / 'manifest.json') == manual
        assert mine in profile.read_json(profileTree / 'manifest.json')['Pages']['Pages']

    def test_removal_never_reaches_a_hand_built_page(self, profileTree, spec):
        parent = profile.read_json(profileTree / 'manifest.json')
        mine = 'MANUAL01.sdProfile'
        parent['Pages']['Pages'].append(mine)
        profile.write_json(profileTree / 'manifest.json', parent)
        profile.write_json(
            profileTree / 'profiles' / mine / 'manifest.json',
            {'Actions': {'0,0': handBuiltEntry('Mine')}, 'Name': 'Mine', 'Version': '1.0'},
        )
        profile.ensure_pages(2, spec=spec)
        profile.ensure_pages(0, spec=spec)
        assert (profileTree / 'profiles' / mine / 'manifest.json').exists()


class TestResync:
    def test_page_meta_is_renumbered_after_a_removal(self, profileTree, spec):
        pages = profile.ensure_pages(3, spec=spec, label='acq4')['pages']
        # drop the middle page and check the last one is renumbered from 2 to 1
        survivor = pages[2]
        result = profile.ensure_pages(2, spec=spec, label='acq4')
        assert survivor in result['removed']

        for index, folder in enumerate(result['pages']):
            manifest = readPage(profileTree, folder)
            assert manifest['Name'] == f'acq4 {index + 1}'
            for settings in generatedSettings(manifest).values():
                assert settings['pageIndex'] == index
                assert settings['pageLabel'] == f'acq4 {index + 1}'

    def test_page_index_matches_the_returned_page_order(self, profileTree, spec):
        result = profile.ensure_pages(3, spec=spec)
        for index, folder in enumerate(result['pages']):
            settings = next(iter(generatedSettings(readPage(profileTree, folder)).values()))
            assert settings['pageIndex'] == index

    def test_resync_leaves_hand_built_keys_on_a_generated_page_alone(self, profileTree, spec):
        folder = profile.ensure_pages(2, spec=spec)['pages'][1]
        manifest = readPage(profileTree, folder)
        manifest['Actions']['0,0'] = handBuiltEntry('Squatter')
        profile.write_json(profileTree / 'profiles' / folder / 'manifest.json', manifest)

        profile.resync_page_meta(profileTree, [folder], 'acq4')
        assert readPage(profileTree, folder)['Actions']['0,0'] == handBuiltEntry('Squatter')


class TestPageSwitchingIsNotOurs:
    """acq4 places no page-change action and reserves no position for one.

    Where a page-switch control lives is configured by the user in VSD Craft, so the only
    obligation here is not to destroy theirs -- see :class:`TestUserPlacedKeysSurvive`.
    """

    def test_a_generated_page_holds_nothing_but_the_configured_layout(self, profileTree, spec):
        folder = profile.ensure_pages(1, spec=spec)['pages'][0]
        actions = readPage(profileTree, folder)['Actions']
        # exactly the spec's 13 keys, no page-change action and no reserved position
        assert set(actions) == set(profile.spec_layout(spec))
        assert not [e for e in actions.values() if e['UUID'] == PAGE_CHANGE_UUID]

    def test_a_page_change_key_on_the_parent_page_is_not_copied_anywhere(self, profileTree, spec):
        parent = profile.read_json(profileTree / 'manifest.json')
        parent['Actions']['4,0'] = pageChangeEntry()
        profile.write_json(profileTree / 'manifest.json', parent)

        for folder in profile.ensure_pages(2, spec=spec)['pages']:
            # the parent page is a page like any other; its keys are not ours to inherit
            assert '4,0' not in readPage(profileTree, folder)['Actions']

    def test_the_strays_on_the_parent_page_are_never_claimed(self, profileTree, spec):
        """The rig's live ``-1,-1`` acq4-UUID key has no generator tag, so it is not ours."""
        assert profile.is_managed({'Actions': {'-1,-1': strayEntry()}}) is False
        result = profile.ensure_pages(1, spec=spec)
        parent = profile.read_json(profileTree / 'manifest.json')
        assert parent['Actions']['-1,-1'] == strayEntry()
        assert result['pages'] and profileTree.name not in result['pages']


class TestUserPlacedKeysSurvive:
    """A generated page is rewritten wholesale, so untagged keys on it must be carried."""

    def test_a_user_placed_page_change_key_survives_regeneration(self, profileTree):
        narrow = profile.GridSpec(button_rows=2, button_cols=5, dial_rows=1, dial_cols=3)
        folder = profile.ensure_pages(1, spec=narrow)['pages'][0]

        # the user adds a page-change control in VSD Craft, on a free knob slot
        manifest = readPage(profileTree, folder)
        manifest['Actions']['4,0'] = pageChangeEntry()
        profile.write_json(profileTree / 'profiles' / folder / 'manifest.json', manifest)

        # a 'dials' change drifts the layout, so the page is regenerated in place
        wide = profile.GridSpec(button_rows=2, button_cols=5, dial_rows=1, dial_cols=4)
        result = profile.ensure_pages(1, spec=wide)
        assert result['rewritten'] == [folder]

        after = readPage(profileTree, folder)['Actions']
        assert after['4,0'] == pageChangeEntry()  # verbatim, at its own position
        assert after['3,0']['UUID'] == f'{profile.PLUGIN_UUID}.knob'  # and the new dial

    def test_a_user_placed_key_does_not_by_itself_make_a_page_stale(self, profileTree, spec):
        folder = profile.ensure_pages(1, spec=spec)['pages'][0]
        manifest = readPage(profileTree, folder)
        manifest['Actions']['4,0'] = pageChangeEntry()
        profile.write_json(profileTree / 'profiles' / folder / 'manifest.json', manifest)

        result = profile.ensure_pages(1, spec=spec)
        assert result['changed'] is False
        assert result['rewritten'] == []

    def test_a_key_the_user_put_over_a_generated_one_is_restored_loudly(self, profileTree, spec):
        """Overwriting a generated key in VSD Craft is the conflict, and it is reachable.

        The page then no longer reports that panel position, so it reads as drifted and is
        regenerated -- at which point the configured control and the user's key want the
        same position.
        """
        folder = profile.ensure_pages(1, spec=spec)['pages'][0]
        manifest = readPage(profileTree, folder)
        manifest['Actions']['2,0'] = pageChangeEntry()  # on top of dial (0, 2)
        profile.write_json(profileTree / 'profiles' / folder / 'manifest.json', manifest)

        result = profile.ensure_pages(1, spec=spec)
        assert result['rewritten'] == [folder]
        entry = readPage(profileTree, folder)['Actions']['2,0']
        assert entry['Settings']['role'] == 'dial'
        assert (entry['Settings']['row'], entry['Settings']['column']) == (0, 2)

    def test_the_contested_position_warns(self, profileTree, spec, caplog):
        folder = profile.ensure_pages(1, spec=spec)['pages'][0]
        manifest = readPage(profileTree, folder)
        manifest['Actions']['2,0'] = pageChangeEntry()
        profile.write_json(profileTree / 'profiles' / folder / 'manifest.json', manifest)

        with caplog.at_level('WARNING'):
            profile.ensure_pages(1, spec=spec)
        assert 'Panel position 2,0' in caplog.text
        assert 'configured control wins' in caplog.text

    def test_unmanaged_actions_reports_only_what_we_did_not_write(self, profileTree, spec):
        folder = profile.ensure_pages(1, spec=spec)['pages'][0]
        assert profile.unmanaged_actions(profileTree, folder) == {}

        manifest = readPage(profileTree, folder)
        manifest['Actions']['4,0'] = pageChangeEntry()
        profile.write_json(profileTree / 'profiles' / folder / 'manifest.json', manifest)
        assert profile.unmanaged_actions(profileTree, folder) == {'4,0': pageChangeEntry()}

    def test_unmanaged_actions_of_a_page_that_is_not_there_is_empty(self, profileTree):
        assert profile.unmanaged_actions(profileTree, 'NOPE0001.sdProfile') == {}


class TestLayoutDrift:
    def test_a_changed_shape_regenerates_pages_in_place(self, profileTree, spec):
        before = profile.ensure_pages(2, spec=spec)['pages']
        assert len(generatedSettings(readPage(profileTree, before[0]))) == 13

        narrow = profile.GridSpec(button_rows=2, button_cols=3, dial_rows=1, dial_cols=2)
        result = profile.ensure_pages(2, spec=narrow)
        assert result['changed'] is True
        assert sorted(result['rewritten']) == sorted(before)
        assert result['added'] == result['removed'] == []
        # same folders, so page identity survives; new layout inside them
        assert result['pages'] == before
        assert len(generatedSettings(readPage(profileTree, before[0]))) == 8

    def test_a_changed_block_to_panel_mapping_regenerates_pages(self, profileTree, spec):
        """Drift is the *placement* moving, not only the block shape changing.

        A page written by an older mapping keeps the logical addresses the config asks for
        but holds them at the wrong panel positions, and the page count is still right, so
        nothing else would notice it.
        """

        def oldMapping(self, role, row, col):
            # what this module wrote while it took panel row 0 for the top row
            return (int(col), int(row) if role == 'dial' else int(self.dial_rows) + int(row))

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(profile.GridSpec, 'panelPosition', oldMapping)
            before = profile.ensure_pages(1, spec=spec)['pages']
            written = generatedSettings(readPage(profileTree, before[0]))
            # block row 0 on the lower of the two button rows: the reversal being fixed
            assert (written['0,1']['row'], written['0,1']['column']) == (0, 0)

        result = profile.ensure_pages(1, spec=spec)
        assert result['changed'] is True
        assert result['rewritten'] == before
        assert result['added'] == result['removed'] == []

        fixed = generatedSettings(readPage(profileTree, before[0]))
        # same logical addresses, moved to the panel rows they belong on
        assert (fixed['0,2']['row'], fixed['0,2']['column']) == (0, 0)
        assert (fixed['0,1']['row'], fixed['0,1']['column']) == (1, 0)

    def test_an_unchanged_shape_is_not_rewritten(self, profileTree, spec):
        profile.ensure_pages(2, spec=spec)
        assert profile.ensure_pages(2, spec=spec)['rewritten'] == []


class TestBackup:
    def test_the_manifest_is_backed_up_exactly_once(self, profileTree, spec):
        backupPath = profileTree / ('manifest.json' + profile.BACKUP_SUFFIX)
        original = (profileTree / 'manifest.json').read_text(encoding='utf-8')

        profile.ensure_pages(1, spec=spec)
        assert backupPath.exists()
        assert backupPath.read_text(encoding='utf-8') == original

        stamp = backupPath.stat().st_mtime_ns
        profile.ensure_pages(3, spec=spec)
        # the second write must not overwrite the pristine copy with a generated one
        assert backupPath.stat().st_mtime_ns == stamp
        assert backupPath.read_text(encoding='utf-8') == original


class TestCurrentPage:
    """acq4 does not choose the page; it only refuses to leave a dangling reference.

    Page switching is a VSD Craft feature. The one write to ``Pages.Current`` this module
    makes is housekeeping for a page it has just deleted -- without it the profile names a
    folder that is no longer there -- so it is pinned here, both to keep it working and so
    that it is not mistaken for a leftover of page control and deleted.
    """

    def test_removing_the_current_page_falls_back_to_the_parent_page(self, profileTree, spec):
        pages = profile.ensure_pages(3, spec=spec)['pages']
        parent = profile.read_json(profileTree / 'manifest.json')
        parent.setdefault('Pages', {})['Current'] = pages[2]
        profile.write_json(profileTree / 'manifest.json', parent)

        result = profile.ensure_pages(2, spec=spec)
        assert result['removed'] == [pages[2]]
        parent = profile.read_json(profileTree / 'manifest.json')
        # the parent page always exists; the deleted folder does not
        assert parent['Pages']['Current'] == profileTree.name
        assert not (profileTree / 'profiles' / pages[2]).exists()

    def test_a_surviving_current_page_is_left_alone(self, profileTree, spec):
        pages = profile.ensure_pages(3, spec=spec)['pages']
        parent = profile.read_json(profileTree / 'manifest.json')
        parent.setdefault('Pages', {})['Current'] = pages[0]
        profile.write_json(profileTree / 'manifest.json', parent)

        profile.ensure_pages(2, spec=spec)
        parent = profile.read_json(profileTree / 'manifest.json')
        assert parent['Pages']['Current'] == pages[0]

    def test_generating_pages_does_not_choose_one(self, profileTree, spec):
        # whichever page the profile arrived pointing at is the user's choice, and adding
        # acq4 pages must not override it
        before = profile.read_json(profileTree / 'manifest.json')['Pages']['Current']
        profile.ensure_pages(2, spec=spec)
        parent = profile.read_json(profileTree / 'manifest.json')
        assert parent['Pages']['Current'] == before

    def test_there_is_no_page_setter_to_call(self, profileTree):
        # deliberately absent: writing Pages.Current to drive the panel is page control,
        # and page control belongs to VSD Craft
        assert not hasattr(profile, 'set_current_page')


class TestMeta:
    def test_missing_or_broken_meta_reads_as_empty(self, tmp_path):
        assert profile.read_meta(tmp_path / 'absent.json') == {}
        broken = tmp_path / 'broken.json'
        broken.write_text('{not json', encoding='utf-8')
        assert profile.read_meta(broken) == {}

    def test_wait_for_plugin_times_out_without_a_republish(self, tmp_path):
        assert profile.wait_for_plugin(tmp_path / 'absent.json', timeout=0.01) is False

    def test_wait_for_plugin_accepts_a_newer_file(self, tmp_path):
        meta = tmp_path / 'ws-meta.json'
        meta.write_text('{}', encoding='utf-8')
        assert profile.wait_for_plugin(meta, newer_than=0.0, timeout=0.5) is True
        assert profile.wait_for_plugin(meta, newer_than=2e9, timeout=0.01) is False
