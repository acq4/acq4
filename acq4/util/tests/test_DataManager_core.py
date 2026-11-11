"""Tests for DataManager handles: the handle cache, .index metadata, and file operations."""

import ctypes
import gc
import logging
import subprocess
import os
import pickle
import sys
import threading
import unicodedata
import weakref
from collections import OrderedDict

import numpy as np
import pytest
from MetaArray import MetaArray
from pyqtgraph.configfile import writeConfigFile

import acq4.util.DataManager as dm
from acq4.util.DataManager import DirHandle, FileHandle
from acq4.util.DataManager.common import (
    CASE_FOLDING,
    abspath,
    foldCase,
    isCaseFolding,
    isCaseInsensitiveDir,
    longPath,
)

caseFolding = pytest.mark.skipif(not CASE_FOLDING, reason="needs a case-insensitive filesystem")
windows = pytest.mark.skipif(sys.platform != "win32", reason="Windows only")


def shortPath(path):
    """Return the Windows 8.3 short form of existing *path*."""
    buf = ctypes.create_unicode_buffer(32768)
    ctypes.windll.kernel32.GetShortPathNameW(path, buf, len(buf))
    return buf.value


@pytest.fixture
def shortNamed(tmp_path):
    """A managed directory whose long name differs from its 8.3 short name."""
    path = tmp_path / "Long Directory Name"
    path.mkdir()
    short = shortPath(str(path))
    if not short or os.path.basename(short) == path.name:
        pytest.skip("volume does not generate 8.3 short names")
    handle = dm.getDirHandle(str(path))
    handle.createIndex()
    return handle, short


def ma(n=4):
    return MetaArray(np.arange(n, dtype=float))


def diskIndex(dirHandle):
    """Return the index of *dirHandle* as a fresh, uncached handle reads it from disk."""
    return DirHandle(dirHandle.name(), dirHandle.manager)._readIndex()


def diskInfo(handle):
    """Return *handle*'s info as a fresh, uncached handle reads it from disk."""
    if handle.isDir():
        return dict(DirHandle(handle.name(), handle.manager).info())
    parent = DirHandle(os.path.dirname(handle.name()), handle.manager)
    return dict(parent._fileInfo(handle.shortName()))


@pytest.fixture
def root(tmp_path):
    handle = dm.getDirHandle(str(tmp_path))
    handle.createIndex()
    return handle


@pytest.fixture
def caseSensitive(tmp_path):
    """A managed directory with Windows per-directory case sensitivity enabled."""
    if sys.platform != "win32":
        pytest.skip("Windows only")
    path = tmp_path / "CaseSensitive"
    path.mkdir()
    result = subprocess.run(
        ["fsutil", "file", "setCaseSensitiveInfo", str(path), "enable"], capture_output=True
    )
    if result.returncode != 0:
        pytest.skip("cannot enable per-directory case sensitivity")
    handle = dm.getDirHandle(str(path))
    handle.createIndex()
    return handle


def touch(dirHandle, name):
    with open(os.path.join(dirHandle.name(), name), "w"):
        pass


@pytest.fixture
def unmanaged(tmp_path):
    path = tmp_path / "plain"
    path.mkdir()
    return dm.getDirHandle(str(path))


class TestHandleCache:
    def test_singleton_manager(self):
        assert dm.getDataManager() is dm.getDataManager()
        with pytest.raises(ValueError):
            dm.DataManager()

    def test_same_path_gives_same_handle(self, root):
        sub = root.mkdir("Sub")
        f = sub.writeFile(ma(), "data")
        assert dm.getDirHandle(sub.name()) is sub
        assert dm.getHandle(sub.name()) is sub
        assert root["Sub"] is sub
        assert root.getDir("Sub") is sub
        assert dm.getFileHandle(f.name()) is f
        assert sub["data.ma"] is f
        assert root[os.path.join("Sub", "data.ma")] is f

    def test_equivalent_spellings_share_a_handle(self, root):
        sub = root.mkdir("Sub")
        assert dm.getHandle(sub.name() + os.sep) is sub
        assert dm.getHandle(os.path.join(root.name(), "Sub", "..", "Sub")) is sub
        assert dm.getHandle(os.path.join(root.name(), ".", "Sub")) is sub
        assert root["/Sub"] is sub
        assert root[os.sep + "Sub"] is sub

    def test_relative_path(self, root, monkeypatch):
        sub = root.mkdir("Sub")
        monkeypatch.chdir(root.name())
        assert dm.getHandle("Sub") is sub

    @caseFolding
    def test_case_variants_share_a_handle(self, root):
        sub = root.mkdir("Sub")
        f = sub.writeFile(ma(), "Clamp1")
        assert dm.getHandle(sub.name().upper()) is sub
        assert dm.getHandle(sub.name().lower()) is sub
        assert root["sub"]["CLAMP1.MA"] is f

    def test_handle_type(self, root):
        sub = root.mkdir("Sub")
        f = root.createFile("notes.txt")
        assert type(dm.getHandle(sub.name())) is DirHandle
        assert type(dm.getHandle(f.name())) is FileHandle

    def test_get_handle_of_missing_path_raises(self, root):
        missing = os.path.join(root.name(), "missing")
        for name in (missing, missing + os.sep, missing + "/"):
            with pytest.raises(FileNotFoundError):
                dm.getHandle(name)
        with pytest.raises(FileNotFoundError):
            root["missing"]
        with pytest.raises(FileNotFoundError):
            dm.getInfo(missing)
        with pytest.raises(FileNotFoundError):
            root.isDir("missing")

    def test_explicit_handles_for_missing_paths(self, root):
        d = dm.getDirHandle(os.path.join(root.name(), "NewDir"))
        f = dm.getFileHandle(os.path.join(root.name(), "new.txt"))
        assert type(d) is DirHandle and not d.exists()
        assert type(f) is FileHandle and not f.exists()

    def test_file_handle_for_uncached_directory_raises(self, root):
        os.mkdir(os.path.join(root.name(), "Plain"))
        with pytest.raises(IsADirectoryError):
            dm.getFileHandle(os.path.join(root.name(), "Plain"))

    def test_dir_handle_for_uncached_file_raises(self, root):
        touch(root, "plain.txt")
        with pytest.raises(NotADirectoryError):
            dm.getDirHandle(os.path.join(root.name(), "plain.txt"))

    def test_conflicting_cached_types_raise(self, root):
        dirPath = os.path.join(root.name(), "AsDir")
        filePath = os.path.join(root.name(), "AsFile")
        dm.getDirHandle(dirPath)
        dm.getFileHandle(filePath)
        with pytest.raises(TypeError):
            dm.getFileHandle(dirPath)
        with pytest.raises(TypeError):
            dm.getDirHandle(filePath)
        with pytest.raises(TypeError):
            dm.getDirHandle(filePath, create=True)
        assert not os.path.exists(filePath)

    def test_mkdir_where_dir_handle_was_cached_first(self, root):
        early = root.getDir("Later")
        assert not early.exists()
        sub = root.mkdir("Later", info={"a": 1})
        assert sub is early
        assert sub.exists() and sub.isManaged()
        assert sub.info()["a"] == 1

    def test_mkdir_where_file_handle_was_cached_first(self, root):
        dm.getFileHandle(os.path.join(root.name(), "Later"))
        with pytest.raises(TypeError):
            root.mkdir("Later")
        assert not os.path.exists(os.path.join(root.name(), "Later"))
        assert not root.isManaged("Later")

    def test_write_file_where_dir_handle_was_cached_first(self, root):
        root.getDir("data.ma")
        with pytest.raises(TypeError):
            root.writeFile(ma(), "data")
        assert not os.path.exists(os.path.join(root.name(), "data.ma"))

    def test_cached_handle_contradicted_by_disk_raises(self, root):
        dirPath = os.path.join(root.name(), "WasDir")
        filePath = os.path.join(root.name(), "WasFile")
        dm.getDirHandle(dirPath)
        dm.getFileHandle(filePath)
        touch(root, "WasDir")
        os.mkdir(filePath)
        with pytest.raises(NotADirectoryError):
            dm.getDirHandle(dirPath)
        with pytest.raises(TypeError):
            dm.getHandle(dirPath)
        with pytest.raises(IsADirectoryError):
            dm.getFileHandle(filePath)
        with pytest.raises(TypeError):
            dm.getHandle(filePath)

    def test_pickling_deleted_handle_raises(self, root):
        f = root.createFile("a.txt")
        f.delete()
        with pytest.raises(Exception, match="deleted"):
            pickle.dumps(f)

    def test_create_file_where_dir_handle_was_cached_first(self, root):
        root.getDir("notes.txt")
        with pytest.raises(TypeError):
            root.createFile("notes.txt")
        assert not os.path.exists(os.path.join(root.name(), "notes.txt"))

    def test_pickle_returns_cached_handle(self, root):
        sub = root.mkdir("Sub")
        f = sub.writeFile(ma(), "data")
        assert pickle.loads(pickle.dumps(sub)) is sub
        assert pickle.loads(pickle.dumps(f)) is f

    def test_equality_and_hash(self, root):
        a = root.createFile("a.txt")
        b = root.createFile("b.txt")
        assert a == root["a.txt"]
        assert a != b
        assert a != a.name()
        handles = {a, b}
        a.rename("a2.txt")
        assert a in handles
        a.delete()
        b.delete()
        assert a in handles
        assert a == a
        assert a != b

    def test_cleanup_drops_only_unreferenced_handles(self, root):
        kept = root.createFile("kept.txt")
        dropped = root.createFile("dropped.txt")
        ref = weakref.ref(dropped)
        del dropped
        dm.getDataManager().cleanup()
        gc.collect()
        assert root["kept.txt"] is kept
        assert ref() is None
        assert root["dropped.txt"].exists()

    def test_concurrent_lookup_gives_one_handle(self, root):
        os.mkdir(os.path.join(root.name(), "Shared"))
        path = os.path.join(root.name(), "Shared")
        results = []
        barrier = threading.Barrier(8)

        def lookup():
            barrier.wait()
            results.append(dm.getDirHandle(path))

        threads = [threading.Thread(target=lookup) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert len(results) == 8
        assert all(h is results[0] for h in results)


class TestNames:
    def test_names_keep_case(self, root):
        sub = root.mkdir("Cell_A")
        f = sub.writeFile(ma(), "Clamp1")
        t = sub.createFile("Notes.TXT")
        assert sub.shortName() == "Cell_A"
        assert sub.name() == os.path.join(root.name(), "Cell_A")
        assert f.shortName() == "Clamp1.ma"
        assert f.name() == os.path.join(sub.name(), "Clamp1.ma")
        assert t.shortName() == "Notes.TXT"
        assert f.ext() == ".ma"

    def test_iteration_matches_disk(self, root):
        root.mkdir("Cell_A")
        root.writeFile(ma(), "Clamp1")
        root.createFile("Notes.TXT")
        names = sorted(os.listdir(root.name()))
        names.remove(".index")
        assert sorted(h.shortName() for h in root) == names
        assert sorted(root.ls()) == names

    def test_relative_names(self, root):
        a = root.mkdir("A")
        b = a.mkdir("B")
        c = root.mkdir("C")
        f = b.writeFile(ma(), "data")
        assert f.name(relativeTo=root) == os.path.join("A", "B", "data.ma")
        assert f.name(relativeTo=c) == os.path.join("..", "A", "B", "data.ma")
        assert root.name(relativeTo=f) == os.path.join("..", "..", "..")
        assert b.name(relativeTo=b) == ""

    @caseFolding
    def test_relative_name_from_differently_cased_handle(self, root):
        sub = root.mkdir("Sub")
        sub.writeFile(ma(), "Data")
        f = dm.getHandle(os.path.join(root.name().upper(), "SUB", "DATA.MA"))
        assert foldCase(f.name(relativeTo=root)) == foldCase(os.path.join("Sub", "Data.ma"))

    def test_parent(self, root):
        sub = root.mkdir("Sub")
        f = sub.writeFile(ma(), "data")
        assert f.parent() is sub
        assert sub.parent() is root
        assert f.isGrandchildOf(root)
        assert root.isGrandparentOf(f)
        assert not sub.isGrandchildOf(f)


class TestMetaInfo:
    def test_written_file_info(self, root):
        f = root.writeFile(ma(), "Clamp1", info={"device": "Clamp1"})
        info = f.info()
        assert info["device"] == "Clamp1"
        assert info["__object_type__"] == "MetaArray"
        assert "__timestamp__" in info
        assert root["Clamp1.ma"].info()["device"] == "Clamp1"
        assert diskInfo(f)["device"] == "Clamp1"
        assert "Clamp1.ma" in diskIndex(root)

    def test_store_result_flow(self, root):
        """Mirror DeviceTask.storeResult: write under the device name, then annotate."""
        protocol = root.mkdir("Protocol", autoIncrement=True)
        f = protocol.writeFile(ma(), "Clamp1")
        f.setInfo(mode="VC")
        protocol.setInfo({("Clamp1", "primary"): 0.5})
        assert f.info()["mode"] == "VC"
        assert f.info()["__object_type__"] == "MetaArray"
        assert protocol.info()[("Clamp1", "primary")] == 0.5
        assert diskInfo(f)["mode"] == "VC"
        assert diskInfo(protocol)[("Clamp1", "primary")] == 0.5
        assert [k for k in diskIndex(protocol) if k != "."] == ["Clamp1.ma"]

    def test_set_info_merges(self, root):
        f = root.writeFile(ma(), "data", info={"a": 1})
        f.setInfo(b=2)
        f.setInfo({"a": 3})
        assert {k: f.info()[k] for k in "ab"} == {"a": 3, "b": 2}
        root.setInfo(x=1)
        root.setInfo(y=2)
        assert (root.info()["x"], root.info()["y"]) == (1, 2)

    def test_info_round_trips_value_types(self, root):
        values = {
            "int": 7,
            "float": 1.5e-12,
            "str": "Clamp1 primary",
            "none": None,
            "bool": True,
            "list": [1, 2.5, "x"],
            "nested": {"inner": {"deep": [1, 2]}},
            "array": np.array([[1.0, 2.0], [3.0, 4.0]]),
            ("tuple", "key"): 3,
        }
        f = root.writeFile(ma(), "data", info=values)
        for source in (dict(f.info()), diskInfo(f)):
            for k, v in values.items():
                if isinstance(v, np.ndarray):
                    np.testing.assert_array_equal(source[k], v)
                else:
                    assert source[k] == v, k

    def test_info_is_read_only(self, root):
        f = root.writeFile(ma(), "data", info={"a": 1})
        with pytest.raises(Exception):
            f.info()["a"] = 2
        with pytest.raises(Exception):
            root.info()["new"] = 1
        assert f.info()["a"] == 1

    def test_get_info_returns_independent_copy(self, root):
        f = root.writeFile(ma(), "data", info={"nested": {"a": 1}})
        copy = dm.getInfo(f.name())
        copy["nested"]["a"] = 2
        assert f.info()["nested"]["a"] == 1

    def test_caller_info_is_not_mutated_or_aliased(self, root):
        info = {"a": 1}
        f = root.writeFile(ma(), "data", info=info)
        sub = root.mkdir("Sub", info=info)
        c = root.createFile("c.txt", info=dict(info))
        assert info == {"a": 1}
        info["a"] = 99
        assert f.info()["a"] == 1
        assert sub.info()["a"] == 1
        assert c.info()["a"] == 1

    def test_set_info_after_append_does_not_alias(self, root):
        info = {"a": 1}
        f = root.createFile("c.txt")
        f.setInfo(info)
        info["a"] = 2
        assert f.info()["a"] == 1

    def test_unmanaged_directory(self, unmanaged):
        assert not unmanaged.isManaged()
        assert dict(unmanaged.info()) == {}
        with open(os.path.join(unmanaged.name(), "raw.txt"), "w") as fd:
            fd.write("x")
        assert dict(unmanaged["raw.txt"].info()) == {}
        assert not unmanaged["raw.txt"].isManaged()
        unmanaged.setInfo(a=1)
        assert unmanaged.isManaged()
        assert unmanaged.info()["a"] == 1

    def test_index_reloads_after_external_change(self, root):
        f = root.writeFile(ma(), "data", info={"a": 1})
        assert f.info()["a"] == 1
        other = DirHandle(root.name(), root.manager)
        other._setFileInfo("data.ma", {"a": 2})
        # Ensure the index mtime differs on filesystems with coarse timestamps.
        mtime = os.path.getmtime(other._indexFile()) + 10
        os.utime(other._indexFile(), (mtime, mtime))
        assert f.info()["a"] == 2

    def test_index_deleted_externally_raises(self, root):
        root.setInfo(a=1)
        f = root.createFile("a.txt")
        os.remove(root._indexFile())
        with pytest.raises(FileNotFoundError):
            root.info()
        with pytest.raises(FileNotFoundError):
            f.info()

    def test_meta_signal(self, root):
        f = root.createFile("c.txt")
        changes = []
        f.sigChanged.connect(lambda h, change, args: changes.append((h, change)))
        f.setInfo(a=1)
        assert (f, "meta") in changes


@caseFolding
class TestCaseInsensitiveIndex:
    def test_handle_cached_with_other_case_reads_info(self, root):
        stale = dm.getFileHandle(os.path.join(root.name(), "clamp1.ma"))  # cached before the file exists
        f = root.writeFile(ma(), "Clamp1", info={"device": "Clamp1"})
        assert f is stale
        assert f.shortName() == "Clamp1.ma"
        assert f.info()["device"] == "Clamp1"
        assert f.isManaged()
        assert f.fileType() == "MetaArray"

    def test_set_info_through_other_case_updates_existing_entry(self, root):
        stale = dm.getFileHandle(os.path.join(root.name(), "clamp1.ma"))
        root.writeFile(ma(), "Clamp1", info={"a": 1})
        stale.setInfo(b=2)
        assert list(k for k in diskIndex(root) if k != ".") == ["Clamp1.ma"]
        assert diskIndex(root)["Clamp1.ma"]["b"] == 2

    def test_legacy_split_entries_are_merged(self, root):
        """Older versions could record one file's info under two spellings."""
        ma().write(os.path.join(root.name(), "Clamp1.ma"))
        index = OrderedDict(
            [
                (".", {}),
                ("Clamp1.ma", {"__object_type__": "MetaArray", "a": 1, "b": 1}),
                ("clamp1.ma", {"b": 2}),
            ]
        )
        writeConfigFile(index, os.path.join(root.name(), ".index"))
        f = root["Clamp1.ma"]
        assert {k: f.info()[k] for k in "ab"} == {"a": 1, "b": 2}
        assert f.fileType() == "MetaArray"

        f.setInfo(c=3)
        keys = [k for k in diskIndex(root) if k != "."]
        assert keys == ["Clamp1.ma"]
        assert {k: diskIndex(root)["Clamp1.ma"][k] for k in "abc"} == {"a": 1, "b": 2, "c": 3}

    def test_handle_takes_on_disk_spelling(self, root):
        root.writeFile(ma(), "Clamp1")
        dm.getDataManager().cleanup()
        gc.collect()
        f = dm.getHandle(os.path.join(root.name().upper(), "CLAMP1.MA"))
        assert f.shortName() == "Clamp1.ma"
        assert f.name() == os.path.join(root.name(), "Clamp1.ma")
        f.setInfo(a=1)
        assert [k for k in diskIndex(root) if k != "."] == ["Clamp1.ma"]

    def test_write_over_differently_cased_file_indexes_disk_name(self, root):
        touch(root, "clamp1.cfg")
        f = root.writeFile({"a": 1}, "Clamp1.cfg", fileType="PyQTGraphConfigFile")
        onDisk = [n for n in os.listdir(root.name()) if n != ".index"]
        assert len(onDisk) == 1
        assert f.shortName() == onDisk[0]
        assert [k for k in diskIndex(root) if k != "."] == onDisk

    def test_conflicting_split_entries_warn(self, root, caplog):
        ma().write(os.path.join(root.name(), "Clamp1.ma"))
        index = OrderedDict([(".", {}), ("Clamp1.ma", {"a": 1}), ("clamp1.ma", {"a": 2})])
        writeConfigFile(index, os.path.join(root.name(), ".index"))
        with caplog.at_level(logging.WARNING):
            assert root["Clamp1.ma"].info()["a"] == 2
        assert any("conflicting" in r.getMessage() for r in caplog.records)

    def test_consolidation_keeps_disk_spelling(self, root):
        ma().write(os.path.join(root.name(), "Clamp1.ma"))
        index = OrderedDict([(".", {}), ("CLAMP1.MA", {"a": 1}), ("clamp1.ma", {"b": 2})])
        writeConfigFile(index, os.path.join(root.name(), ".index"))
        root["clamp1.ma"].setInfo(c=3)
        assert [k for k in diskIndex(root) if k != "."] == ["Clamp1.ma"]
        assert {k: diskIndex(root)["Clamp1.ma"][k] for k in "abc"} == {"a": 1, "b": 2, "c": 3}

    def test_forget_removes_every_spelling(self, root):
        ma().write(os.path.join(root.name(), "Clamp1.ma"))
        index = OrderedDict([(".", {}), ("Clamp1.ma", {"a": 1}), ("clamp1.ma", {"b": 2})])
        writeConfigFile(index, os.path.join(root.name(), ".index"))
        root.forget("CLAMP1.MA")
        assert list(diskIndex(root)) == ["."]
        assert not root.isManaged("Clamp1.ma")

    def test_case_only_rename(self, root):
        f = root.writeFile(ma(), "clamp1", info={"a": 1})
        f.rename("Clamp1.ma")
        assert "Clamp1.ma" in os.listdir(root.name())
        assert f.shortName() == "Clamp1.ma"
        assert f.info()["a"] == 1
        assert [k for k in diskIndex(root) if k != "."] == ["Clamp1.ma"]
        assert root["Clamp1.ma"] is f

    def test_case_only_directory_rename_keeps_children(self, root):
        d = root.mkdir("cell")
        f = d.writeFile(ma(), "data", info={"a": 1})
        d.rename("Cell")
        assert "Cell" in os.listdir(root.name())
        assert d.shortName() == "Cell"
        assert f.name() == os.path.join(root.name(), "Cell", "data.ma")
        assert f.info()["a"] == 1
        assert root["Cell"]["data.ma"] is f

    def test_increment_counts_differently_cased_files(self, root):
        root.writeFile(ma(), "clamp1_004.ma")
        assert root.incrementFileName("Clamp1.ma") == "Clamp1_005.ma"

    def test_nearest_log_file_any_case(self, root):
        root.createFile("Log.txt")
        f = root.mkdir("Sub").writeFile(ma(), "data")
        log = f.nearestLogFile()
        assert log is not None
        assert log.shortName().lower() == "log.txt"


class TestWriteFile:
    def test_extension_handling(self, root):
        assert root.writeFile(ma(), "a").shortName() == "a.ma"
        assert root.writeFile(ma(), "b.ma").shortName() == "b.ma"
        assert root.writeFile(ma(), "c.MA").shortName() == "c.MA"

    def test_data_round_trip(self, root):
        data = np.linspace(0, 1, 11)
        f = root.writeFile(MetaArray(data), "data")
        np.testing.assert_array_equal(np.asarray(f.read()), data)

        cfg = {"a": 1, "nested": {"b": [1, 2]}}
        c = root.writeFile(cfg, "Settings.cfg")
        assert c.fileType() == "PyQTGraphConfigFile"
        assert c.read() == cfg

    def test_unwritable_type_raises(self, root):
        with pytest.raises(TypeError):
            root.writeFile(object(), "nothing")

    def test_overwrite_updates_info(self, root):
        root.writeFile(ma(), "data", info={"a": 1, "b": 1})
        f = root.writeFile(ma(8), "data", info={"a": 2})
        assert (f.info()["a"], f.info()["b"]) == (2, 1)
        assert [k for k in diskIndex(root) if k != "."] == ["data.ma"]

    def test_auto_increment(self, root):
        names = [root.writeFile(ma(), "Clamp1", autoIncrement=True).shortName() for _ in range(3)]
        assert names == ["Clamp1_000.ma", "Clamp1_001.ma", "Clamp1_002.ma"]
        assert all(root[n].info()["__object_type__"] == "MetaArray" for n in names)

    def test_create_file(self, root):
        f = root.createFile("Notes.txt", info={"a": 1})
        assert f.exists() and f.isFile()
        assert f.info()["a"] == 1
        os.remove(f.name())  # fails on Windows if the file was left open

    def test_create_file_auto_increment(self, root):
        names = [root.createFile("n.txt", autoIncrement=True).shortName() for _ in range(2)]
        assert names == ["n_000.txt", "n_001.txt"]

    def test_concurrent_writes_are_all_indexed(self, root):
        errors = []

        def writer(n):
            try:
                for i in range(10):
                    root.writeFile(ma(), f"w{n}", autoIncrement=True, info={"n": n, "i": i})
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(n,)) for n in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert errors == []
        index = diskIndex(root)
        assert len([k for k in index if k != "."]) == 40
        assert len(root.ls()) == 40
        assert {(index[k]["n"], index[k]["i"]) for k in index if k != "."} == {
            (n, i) for n in range(4) for i in range(10)
        }

    def test_write_signal(self, root):
        changes = []
        root.sigChanged.connect(lambda h, change, args: changes.append(change))
        root.writeFile(ma(), "data")
        assert "children" in changes


class TestIncrementFileName:
    def test_first_name(self, root):
        assert root.incrementFileName("Clamp1.ma") == "Clamp1_000.ma"
        assert root.incrementFileName("Cell", useExt=False) == "Cell_000"

    def test_continues_after_highest(self, root):
        for n in (0, 1, 5):
            root.createFile(f"img_{n:03d}.tif")
        assert root.incrementFileName("img.tif") == "img_006.tif"

    def test_counts_numerically_past_999(self, root):
        root.createFile("img_999.tif")
        root.createFile("img_1000.tif")
        assert root.incrementFileName("img.tif") == "img_1001.tif"

    def test_name_with_regex_characters(self, root):
        root.createFile("a.b(1)_003.txt")
        root.createFile("aXb(1)_007.txt")
        assert root.incrementFileName("a.b(1).txt") == "a.b(1)_004.txt"

    def test_unreadable_directory_raises(self, root):
        missing = dm.getDirHandle(os.path.join(root.name(), "Missing"))
        with pytest.raises(FileNotFoundError):
            missing.incrementFileName("x.txt")

    def test_ignores_other_extensions_and_prefixes(self, root):
        root.createFile("img_004.png")
        root.createFile("myimg_009.tif")
        root.createFile("img_002.tif")
        assert root.incrementFileName("img.tif") == "img_003.tif"


class TestDirectories:
    def test_mkdir(self, root):
        sub = root.mkdir("Cell", info={"a": 1})
        assert sub.isDir() and sub.exists() and sub.isManaged()
        assert sub.info()["a"] == 1
        assert "__timestamp__" in sub.info()
        assert root.isManaged("Cell")
        assert "__timestamp__" in diskIndex(root)["Cell"]

    def test_mkdir_existing_raises(self, root):
        root.mkdir("Cell")
        with pytest.raises(Exception):
            root.mkdir("Cell")

    def test_mkdir_auto_increment(self, root):
        names = [root.mkdir("Cell", autoIncrement=True).shortName() for _ in range(3)]
        assert names == ["Cell_000", "Cell_001", "Cell_002"]

    def test_get_dir(self, root):
        sub = root.getDir("Sub", create=True)
        assert sub.exists()
        assert root.getDir("Sub") is sub
        assert root.getDir("Sub", create=True) is sub
        missing = root.getDir("Missing")
        assert not missing.exists()
        assert root.dirExists("Sub")
        assert not root.dirExists("Missing")
        assert root.subDirs() == ["Sub"]

    def test_get_file_indexes_unmanaged_file(self, root):
        with open(os.path.join(root.name(), "raw.txt"), "w") as fd:
            fd.write("x")
        assert not root.isManaged("raw.txt")
        f = root.getFile("raw.txt")
        assert f is root["raw.txt"]
        assert root.isManaged("raw.txt")

    def test_index_file_and_forget(self, root):
        with open(os.path.join(root.name(), "raw.txt"), "w") as fd:
            fd.write("x")
        root.indexFile("raw.txt", info={"a": 1})
        assert root["raw.txt"].info()["a"] == 1
        with pytest.raises(Exception):
            root.indexFile("raw.txt", protect=True)
        with pytest.raises(Exception):
            root.indexFile("missing.txt")
        root.forget("raw.txt")
        assert not root.isManaged("raw.txt")
        assert "raw.txt" not in diskIndex(root)
        root.forget("raw.txt")
        root.forget("never-indexed.txt")

    def test_index_file_creates_index(self, unmanaged):
        with open(os.path.join(unmanaged.name(), "raw.txt"), "w") as fd:
            fd.write("x")
        unmanaged.indexFile("raw.txt")
        assert unmanaged.isManaged()
        assert unmanaged.isManaged("raw.txt")

    def test_check_index_drops_missing_files(self, root):
        root.setInfo(a=1)
        root.createFile("gone.txt")
        root.createFile("kept.txt")
        os.remove(os.path.join(root.name(), "gone.txt"))
        root.checkIndex()
        assert list(diskIndex(root)) == [".", "kept.txt"]
        assert root.info()["a"] == 1

    def test_exists(self, root):
        root.createFile("a.txt")
        root.mkdir("Sub")
        assert root.exists("a.txt")
        assert root.exists("Sub")
        assert not root.exists("b.txt")
        assert root.isFile("a.txt")
        assert not root.isFile("Sub")
        assert root.isDir("Sub")

    def test_has_children(self, root):
        sub = root.mkdir("Sub")
        assert not sub.hasChildren()
        sub.createFile("a.txt")
        assert sub.hasChildren()
        assert sub.hasMatchingChildren(lambda h: h.shortName() == "a.txt")
        assert not sub.hasMatchingChildren(lambda h: h.isDir())

    def test_nearest_log_file(self, root):
        log = root.createFile("log.txt")
        f = root.mkdir("A").mkdir("B").writeFile(ma(), "data")
        assert f.nearestLogFile() is log
        nearer = root["A"].createFile("log.json")
        assert f.nearestLogFile() is nearer


class TestListing:
    def test_ls_excludes_index(self, root):
        root.createFile("a.txt")
        assert ".index" not in root.ls()
        assert root.ls() == ["a.txt"]

    def test_ls_date_order_uses_index_timestamps(self, root):
        root.createFile("b.txt", info={"__timestamp__": 100.0})
        root.createFile("a.txt", info={"__timestamp__": 200.0})
        root.createFile("c.txt", info={"__timestamp__": 50.0})
        assert root.ls() == ["c.txt", "b.txt", "a.txt"]

    def test_ls_alpha_and_unsorted(self, root):
        for n in ("b.txt", "a.txt", "c.txt"):
            root.createFile(n)
        assert root.ls(sortMode="alpha") == ["a.txt", "b.txt", "c.txt"]
        root.mkdir("z_dir")
        root.mkdir("m_dir")
        assert root.ls(sortMode="alpha") == ["m_dir", "z_dir", "a.txt", "b.txt", "c.txt"]
        assert sorted(root.ls(sortMode=None)) == ["a.txt", "b.txt", "c.txt", "m_dir", "z_dir"]
        with pytest.raises(ValueError):
            root.ls(sortMode="size")

    def test_ls_normcase(self, root):
        root.createFile("Mixed.TXT")
        assert root.ls(normcase=True) == [os.path.normcase("Mixed.TXT")]

    def test_ls_cache_invalidated_by_changes(self, root):
        root.createFile("a.txt")
        assert root.ls(useCache=True) == ["a.txt"]
        root.createFile("b.txt", info={"__timestamp__": 1e12})
        assert root.ls(useCache=True) == ["a.txt", "b.txt"]
        root["a.txt"].delete()
        assert root.ls(useCache=True) == ["b.txt"]

    def test_ls_returns_copy(self, root):
        root.createFile("a.txt")
        root.ls().append("bogus")
        assert root.ls() == ["a.txt"]


class TestRename:
    def test_rename_file_keeps_info(self, root):
        f = root.writeFile(ma(), "old", info={"a": 1})
        f.rename("New.ma")
        assert f.shortName() == "New.ma"
        assert f.exists()
        assert f.info()["a"] == 1
        assert root["New.ma"] is f
        assert not root.isManaged("old.ma")
        assert [k for k in diskIndex(root) if k != "."] == ["New.ma"]
        assert not os.path.exists(os.path.join(root.name(), "old.ma"))

    def test_rename_onto_existing_raises(self, root):
        a = root.createFile("a.txt", info={"x": 1})
        root.createFile("b.txt")
        with pytest.raises(FileExistsError):
            a.rename("b.txt")
        assert a.shortName() == "a.txt"
        assert a.info()["x"] == 1

    def test_rename_directory_updates_cached_descendants(self, root):
        a = root.mkdir("A", info={"a": 1})
        b = a.mkdir("B")
        f = b.writeFile(ma(), "data", info={"f": 1})
        assert f.parent() is b
        a.rename("A2")
        assert a.name() == os.path.join(root.name(), "A2")
        assert b.name() == os.path.join(root.name(), "A2", "B")
        assert f.name() == os.path.join(root.name(), "A2", "B", "data.ma")
        assert root["A2"] is a
        assert root[os.path.join("A2", "B")] is b
        assert root[os.path.join("A2", "B", "data.ma")] is f
        assert f.parent() is b
        assert a.info()["a"] == 1
        assert f.info()["f"] == 1
        assert root.isManaged("A2") and not root.isManaged("A")
        with pytest.raises(FileNotFoundError):
            root[os.path.join("A", "B")]

    def test_rename_carries_handles_for_missing_children(self, root):
        a = root.mkdir("A")
        planned = dm.getFileHandle(os.path.join(a.name(), "planned.txt"))
        a.rename("B")
        assert planned.name() == os.path.join(root.name(), "B", "planned.txt")
        assert dm.getFileHandle(os.path.join(root.name(), "B", "planned.txt")) is planned

    def test_rename_does_not_touch_sibling_with_shared_prefix(self, root):
        a = root.mkdir("A")
        ab = root.mkdir("AB")
        f = ab.writeFile(ma(), "data")
        a.rename("Z")
        assert ab.name() == os.path.join(root.name(), "AB")
        assert f.name() == os.path.join(root.name(), "AB", "data.ma")
        assert root["AB"]["data.ma"] is f

    def test_rename_signal(self, root):
        f = root.createFile("a.txt")
        changes = []
        f.sigChanged.connect(lambda h, change, args: changes.append((change, args)))
        f.rename("b.txt")
        assert ("renamed", (os.path.join(root.name(), "a.txt"), os.path.join(root.name(), "b.txt"))) in changes


class TestMove:
    def test_move_file_keeps_info(self, root):
        src = root.mkdir("Src")
        dst = root.mkdir("Dst")
        f = src.writeFile(ma(), "data", info={"a": 1})
        f.move(dst)
        assert f.name() == os.path.join(dst.name(), "data.ma")
        assert f.parent() is dst
        assert f.info()["a"] == 1
        assert dst["data.ma"] is f
        assert not src.isManaged("data.ma")
        assert "data.ma" in diskIndex(dst)
        assert "data.ma" not in diskIndex(src)

    def test_move_directory_updates_descendants(self, root):
        cell = root.mkdir("Cell", info={"c": 1})
        f = cell.writeFile(ma(), "data", info={"a": 1})
        dst = root.mkdir("Dst")
        cell.move(dst)
        assert cell.name() == os.path.join(dst.name(), "Cell")
        assert f.name() == os.path.join(dst.name(), "Cell", "data.ma")
        assert f.info()["a"] == 1
        assert cell.info()["c"] == 1
        assert dst["Cell"]["data.ma"] is f

    def test_move_onto_existing_raises(self, root):
        src = root.mkdir("Src")
        dst = root.mkdir("Dst")
        f = src.createFile("a.txt")
        dst.createFile("a.txt")
        with pytest.raises(FileExistsError):
            f.move(dst)
        assert f.parent() is src

    def test_move_managed_to_unmanaged_raises(self, root, unmanaged):
        f = root.createFile("a.txt", info={"a": 1})
        with pytest.raises(ValueError):
            f.move(unmanaged)
        assert f.exists()
        assert f.info()["a"] == 1


class TestDelete:
    def test_delete_file(self, root):
        f = root.writeFile(ma(), "data")
        f.delete()
        assert not f.exists()
        assert f.path is None
        assert not root.isManaged("data.ma")
        assert root.ls() == []
        with pytest.raises(Exception):
            f.info()

    def test_delete_directory_invalidates_descendants(self, root):
        cell = root.mkdir("Cell")
        sub = cell.mkdir("Sub")
        f = sub.writeFile(ma(), "data")
        cell.delete()
        for h in (cell, sub, f):
            assert not h.exists()
            assert h.path is None
        assert not root.isManaged("Cell")
        new = root.mkdir("Cell")
        assert new is not cell
        assert new.exists()

    def test_delete_signal(self, root):
        f = root.createFile("a.txt")
        changes = []
        f.sigChanged.connect(lambda h, change, args: changes.append(change))
        f.delete()
        assert "deleted" in changes


class TestPathNormalization:
    def test_case_folding_platforms(self):
        assert isCaseFolding("win32")
        assert isCaseFolding("darwin")
        assert not isCaseFolding("linux")

    def test_fold_case_windows(self):
        assert foldCase("C:/Data/Clamp1.MA", "win32") == foldCase(r"c:\data\clamp1.ma", "win32")

    def test_fold_case_macos(self):
        nfd = unicodedata.normalize("NFD", "café")
        nfc = unicodedata.normalize("NFC", "café")
        assert nfd != nfc
        assert foldCase(nfd, "darwin") == foldCase(nfc, "darwin")
        assert foldCase("/Data/Clamp1.MA", "darwin") == foldCase("/data/clamp1.ma", "darwin")

    def test_fold_case_case_sensitive_platform(self):
        assert foldCase("/Data/Clamp1.MA", "linux") == "/Data/Clamp1.MA"

    def test_long_path_leaves_plain_paths_alone(self, tmp_path):
        path = str(tmp_path / "plain")
        assert longPath(path) == path

    @windows
    def test_long_path_expands_short_names(self, shortNamed):
        handle, short = shortNamed
        assert longPath(short) == handle.name()

    @windows
    def test_long_path_keeps_missing_tail(self, shortNamed):
        handle, short = shortNamed
        assert longPath(os.path.join(short, "Not", "Yet")) == os.path.join(handle.name(), "Not", "Yet")

    @windows
    def test_long_path_unresolvable(self):
        path = r"Q:\NOSUCH~1\x"
        if os.path.exists("Q:/"):
            pytest.skip("Q: exists")
        assert longPath(path) == path


@windows
class TestShortNames:
    def test_short_and_long_paths_share_a_handle(self, shortNamed):
        handle, short = shortNamed
        assert dm.getDirHandle(short) is handle
        assert dm.getHandle(short.lower()) is handle
        assert handle.name() == longPath(short)

    def test_handle_from_short_path_has_long_name(self, tmp_path):
        path = tmp_path / "Another Long Name"
        path.mkdir()
        short = shortPath(str(path))
        if os.path.basename(short) == path.name:
            pytest.skip("volume does not generate 8.3 short names")
        handle = dm.getDirHandle(short)
        assert handle.shortName() == "Another Long Name"
        assert dm.getDirHandle(str(path)) is handle

    def test_files_under_short_path(self, shortNamed):
        handle, short = shortNamed
        f = dm.getDirHandle(short).writeFile(ma(), "Clamp1", info={"a": 1})
        assert f is handle["Clamp1.ma"]
        assert dm.getHandle(os.path.join(short, "Clamp1.ma")) is f
        assert f.name() == os.path.join(handle.name(), "Clamp1.ma")
        assert f.info()["a"] == 1
        assert f.name(relativeTo=dm.getDirHandle(short)) == "Clamp1.ma"

    def test_missing_child_of_short_path(self, shortNamed):
        handle, short = shortNamed
        early = dm.getDirHandle(os.path.join(short, "Later"))
        assert early is handle.getDir("Later")
        assert handle.mkdir("Later") is early

    def test_rename_short_named_directory(self, shortNamed):
        handle, short = shortNamed
        f = handle.writeFile(ma(), "data", info={"a": 1})
        handle.rename("Renamed Directory")
        assert f.name() == os.path.join(os.path.dirname(handle.name()), "Renamed Directory", "data.ma")
        assert f.info()["a"] == 1


@caseFolding
class TestMovedDescendantSpelling:
    def test_child_cached_under_other_case_follows_parent_rename(self, root):
        a = root.mkdir("Alpha")
        a.writeFile(ma(), "Data", info={"a": 1})
        f = dm.getHandle(os.path.join(root.name(), "ALPHA", "DATA.MA"))
        a.rename("Beta")
        assert f.exists()
        assert foldCase(f.name()) == foldCase(os.path.join(root.name(), "Beta", "Data.ma"))
        assert f.info()["a"] == 1
        assert root["Beta"]["Data.ma"] is f


class TestCaseSensitiveDirectory:
    """Windows directories can be made case-sensitive; nothing may assume case folding there."""

    def test_probe(self, root, caseSensitive):
        assert isCaseInsensitiveDir(root.name()) is True
        assert isCaseInsensitiveDir(caseSensitive.name()) is False

    def test_probe_without_index_uses_entries(self, caseSensitive):
        sub = os.path.join(caseSensitive.name(), "plain")
        os.mkdir(sub)
        assert isCaseInsensitiveDir(sub) is None
        with open(os.path.join(sub, "123"), "w"):
            pass
        assert isCaseInsensitiveDir(sub) is None
        with open(os.path.join(sub, "Abc"), "w"):
            pass
        assert isCaseInsensitiveDir(sub) is False

    def test_inconclusive_probe_is_not_cached(self, caseSensitive):
        sub = os.path.join(caseSensitive.name(), "plain")
        os.mkdir(sub)
        handle = dm.getDirHandle(sub)
        assert handle._isCaseInsensitive() == CASE_FOLDING
        with open(os.path.join(sub, "Img_000.tif"), "w"):
            pass
        assert handle._isCaseInsensitive() is False
        assert handle.incrementFileName("img.tif") == "img_000.tif"

    def test_delete_leaves_case_variant_sibling_alone(self, caseSensitive):
        os.mkdir(os.path.join(caseSensitive.name(), "a"))
        os.mkdir(os.path.join(caseSensitive.name(), "A"))
        touch(caseSensitive, os.path.join("A", "f.txt"))
        other = dm.getFileHandle(os.path.join(caseSensitive.name(), "A", "f.txt"))
        caseSensitive["a"].delete()
        assert other.path is not None
        assert other.exists()
        assert dm.getFileHandle(other.name()) is other

    def test_rename_leaves_case_variant_sibling_alone(self, caseSensitive):
        os.mkdir(os.path.join(caseSensitive.name(), "a"))
        os.mkdir(os.path.join(caseSensitive.name(), "A"))
        touch(caseSensitive, os.path.join("A", "f.txt"))
        other = dm.getFileHandle(os.path.join(caseSensitive.name(), "A", "f.txt"))
        caseSensitive["a"].rename("b")
        assert other.name() == os.path.join(caseSensitive.name(), "A", "f.txt")
        assert dm.getFileHandle(other.name()) is other

    def test_names_differing_in_case_cannot_share_a_handle(self, caseSensitive):
        touch(caseSensitive, "a.txt")
        touch(caseSensitive, "A.txt")
        caseSensitive["a.txt"]
        with pytest.raises(FileExistsError):
            caseSensitive["A.txt"]

    def test_create_colliding_name_fails_before_writing(self, caseSensitive):
        caseSensitive.createFile("a.txt")
        with pytest.raises(FileExistsError):
            caseSensitive.createFile("A.txt")
        assert os.listdir(caseSensitive.name()) == [".index", "a.txt"]

    def test_index_keys_are_not_merged(self, caseSensitive, caplog):
        touch(caseSensitive, "a.txt")
        touch(caseSensitive, "A.txt")
        index = OrderedDict([(".", {}), ("a.txt", {"v": 1}), ("A.txt", {"v": 2})])
        writeConfigFile(index, os.path.join(caseSensitive.name(), ".index"))
        fresh = DirHandle(caseSensitive.name(), caseSensitive.manager)
        with caplog.at_level(logging.WARNING):
            assert dict(fresh._fileInfo("a.txt")) == {"v": 1}
            assert dict(fresh._fileInfo("A.txt")) == {"v": 2}
        assert not caplog.records
        assert not fresh.isManaged("A.TXT")

    def test_exists_is_exact(self, caseSensitive):
        touch(caseSensitive, "a.txt")
        assert caseSensitive.exists("a.txt")
        assert not caseSensitive.exists("A.txt")
        assert not caseSensitive.isFile("A.txt")

    def test_increment_is_case_sensitive(self, caseSensitive):
        touch(caseSensitive, "Img_000.tif")
        assert caseSensitive.incrementFileName("img.tif") == "img_000.tif"
        assert caseSensitive.incrementFileName("Img.tif") == "Img_001.tif"

    def test_rename_onto_other_case_raises(self, caseSensitive):
        touch(caseSensitive, "a.txt")
        touch(caseSensitive, "A.txt")
        f = caseSensitive["a.txt"]
        with pytest.raises(FileExistsError):
            f.rename("A.txt")
        assert sorted(os.listdir(caseSensitive.name())) == [".index", "A.txt", "a.txt"]
