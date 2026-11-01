"""CPU controls for Kaggle launch arithmetic, persistence and process shutdown."""

import _thread
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

EXAMPLES = Path(__file__).resolve().parents[1] / "examples/fullcycle003"
spec = importlib.util.spec_from_file_location("fullcycle_kaggle", EXAMPLES / "kaggle_run.py")
launcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(launcher)


class KaggleLauncherControls(unittest.TestCase):
    def test_probe_covers_maximum_shapes_and_repeated_optimizer_updates(self):
        shapes = {s["stage"]: s for s in launcher.probe_shapes(2)}
        self.assertEqual(set(shapes), {"pretrain", "sft", "dpo", "rl"})
        for name, batch, length, accumulation, batches, references in (
            ("pretrain", 8, 512, 2, [8], []),
            ("sft", 4, 1024, 1, [4, 4], []),
            ("dpo", 2, 1024, 1, [2, 2, 2], [0, 1]),
            ("rl", 1, 1024, 1, [4, 1], [0]),
        ):
            shape = shapes[name]
            self.assertEqual(
                (shape["batch_size"], shape["sequence_length"], shape["accumulation"]),
                (batch, length, accumulation),
            )
            self.assertEqual(
                (shape["gradient_batch_sizes"], shape["reference_forward_indices"]),
                (batches, references),
            )
            self.assertEqual(shape["updates"], 2)
        single = {s["stage"]: s for s in launcher.probe_shapes(1)}
        self.assertEqual(single["pretrain"]["accumulation"], 4)
        self.assertEqual(single["sft"]["accumulation"], 2)

    def test_failed_shape_probe_prevents_public_data_acquisition(self):
        with tempfile.TemporaryDirectory() as d:
            with (
                patch.object(launcher, "hardware"),
                patch.object(
                    launcher.subprocess,
                    "run",
                    side_effect=subprocess.CalledProcessError(1, "probe"),
                ),
                patch.dict(
                    sys.modules,
                    {"trainlab.fullcycle.pipeline": SimpleNamespace(prepare_configuration=Mock())},
                ),
            ):
                from trainlab.fullcycle.pipeline import prepare_configuration

                with self.assertRaises(subprocess.CalledProcessError):
                    launcher.worker(
                        SimpleNamespace(
                            output=Path(d),
                            cache=Path(d) / "cache",
                            gpus=2,
                            resume_input=None,
                            prepared_input=None,
                        )
                    )
                prepare_configuration.assert_not_called()

    def test_two_rank_recipe_preserves_work_without_mutating_source(self):
        original = json.loads((EXAMPLES / "tac-10m-full.json").read_bytes())
        single, dual = [launcher.world_config(original, n) for n in (1, 2)]
        for gpus, config in ((1, single), (2, dual)):
            pre = config["stages"][0]
            self.assertEqual(
                pre["steps"] * pre["batch_size"] * pre["gradient_accumulation"] * 512 * gpus,
                200015872,
            )
            rl = config["stages"][-1]
            self.assertEqual(rl["steps"] * rl["batch_size"] * rl["group_size"] * gpus, 256)
        self.assertEqual(original["stages"][0]["gradient_accumulation"], 4)
        self.assertEqual(dual["stages"][-1]["steps"], 32)
        self.assertEqual(dual["model"], original["model"])

    def test_missing_cuda_fails_before_acquisition(self):
        torch = SimpleNamespace(cuda=SimpleNamespace(is_available=lambda: False))
        with patch.dict(sys.modules, {"torch": torch}):
            with self.assertRaisesRegex(ValueError, "real visible T4"):
                launcher.hardware(2)

    def test_other_accelerator_is_rejected(self):
        cuda = SimpleNamespace(
            is_available=lambda: True, device_count=lambda: 2, get_device_name=lambda i: "NVIDIA L4"
        )
        with patch.dict(sys.modules, {"torch": SimpleNamespace(cuda=cuda)}):
            with self.assertRaisesRegex(ValueError, "no accelerator fallback"):
                launcher.hardware(2)

    def test_resume_rejects_a_valid_but_different_recipe_before_probe(self):
        config = launcher.world_config(json.loads((EXAMPLES / "tac-10m-full.json").read_bytes()), 2)
        with tempfile.TemporaryDirectory() as d:
            output = Path(d)
            config["dataset"] = {
                "directory": str(output / "data/release"),
                "manifest_sha256": launcher.RELEASE_SHA256,
                "source_plan_sha256": launcher.PLAN_SHA256,
                "acquisition_sha256": launcher.ACQUISITION_SHA256,
            }
            config["tokenizer"] = {
                "kind": "artifact",
                "artifact_path": str(output / "data/tokenizer.json"),
                "artifact_sha256": launcher.TOKENIZER_SHA256,
            }
            launcher.verify_full_recipe(config, output, 2)
            variants = [copy.deepcopy(config) for _ in range(7)]
            variants[0]["stages"][0]["steps"] = 256
            variants[1]["model"]["layers"] = 4
            variants[2]["dataset"]["manifest_sha256"] = "a" * 64
            variants[3]["tokenizer"]["artifact_sha256"] = "b" * 64
            variants[4]["seed"] += 1
            variants[5]["precision"] = "bf16"
            variants[6]["parameter_target"] = 1000000
            (output / "run").mkdir()
            (output / "run/protocol.json").write_text('{"world_size":2}')
            for changed in variants:
                with self.subTest(config=changed):
                    (output / "run/pipeline.json").write_text(json.dumps(changed))
                    with (
                        patch.object(launcher, "hardware"),
                        patch.object(launcher.subprocess, "run") as probe,
                        patch.dict(
                            sys.modules,
                            {
                                "trainlab.fullcycle.pipeline": SimpleNamespace(
                                    prepare_configuration=None
                                )
                            },
                        ),
                    ):
                        with self.assertRaisesRegex(ValueError, "full-training recipe"):
                            launcher.worker(
                                SimpleNamespace(
                                    output=output, gpus=2, resume_input=None, prepared_input=None
                                )
                            )
                        self.assertFalse(probe.called)

    def test_restore_refuses_existing_targets_and_symlinks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source, output = root / "previous", root / "output"
            for name in ("data", "run"):
                (source / name).mkdir(parents=True)
                (source / name / "fixture.json").write_text("{}")
            output.mkdir()
            launcher.restore_input(source, output)
            self.assertTrue((output / "run/fixture.json").is_file())
            with self.assertRaises(ValueError):
                launcher.restore_input(source, output)
            (source / "run/link").symlink_to(source / "data/fixture.json")
            with self.assertRaises(ValueError):
                launcher.restore_input(source, root / "fresh")

    @unittest.skipUnless(
        launcher.compatible_proc_namespace(), "requires a matching /proc PID namespace"
    )
    def test_budget_sends_interrupt_and_allows_checkpoint_handler(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "saved"
            script = (
                "import signal,time,pathlib\n"
                f"def stop(*args):\n pathlib.Path({str(marker)!r}).write_text('saved')\n"
                " raise SystemExit(0)\n"
                "signal.signal(signal.SIGINT,stop)\n"
                "while True:time.sleep(.05)\n"
            )
            result = launcher.launch([sys.executable, "-c", script], 0.5, grace=2)
            self.assertTrue(result["budget_expired"])
            self.assertEqual(result["returncode"], 0)
            self.assertTrue(marker.exists())

    @unittest.skipUnless(
        launcher.compatible_proc_namespace(), "requires a matching /proc PID namespace"
    )
    def test_operator_interrupt_preserves_checkpoint_grace(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "saved"
            script = (
                "import signal,time,pathlib\n"
                f"def stop(*args):\n time.sleep(.2)\n pathlib.Path({str(marker)!r}).touch()\n"
                " raise SystemExit(0)\n"
                "signal.signal(signal.SIGINT,stop)\n"
                "while True:time.sleep(.05)\n"
            )
            interrupt = threading.Timer(0.5, _thread.interrupt_main)
            interrupt.start()
            try:
                result = launcher.launch([sys.executable, "-c", script], 10, grace=2)
            finally:
                interrupt.cancel()
                interrupt.join()
            self.assertTrue(result["operator_interrupted"])
            self.assertFalse(result["budget_expired"])
            self.assertEqual(result["returncode"], 0)
            self.assertTrue(marker.exists())

    @unittest.skipUnless(
        launcher.compatible_proc_namespace(), "requires a matching /proc PID namespace"
    )
    def test_wrapper_exit_still_gives_child_time_to_save(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "child-saved"
            child = (
                "import signal,time,pathlib\n"
                f"def stop(*args):\n time.sleep(.2)\n pathlib.Path({str(marker)!r}).touch()\n"
                " raise SystemExit(0)\n"
                "signal.signal(signal.SIGINT,stop)\n"
                "signal.signal(signal.SIGTERM,stop)\n"
                "while True:time.sleep(.05)\n"
            )
            wrapper = (
                "import subprocess,sys,signal,time\n"
                f"subprocess.Popen([sys.executable,'-c',{child!r}])\n"
                "def stop(*args):raise SystemExit(0)\n"
                "signal.signal(signal.SIGINT,stop)\n"
                "while True:time.sleep(.05)\n"
            )
            result = launcher.launch([sys.executable, "-c", wrapper], 0.5, grace=1)
            self.assertTrue(result["budget_expired"])
            self.assertTrue(marker.exists())

    @unittest.skipUnless(
        launcher.compatible_proc_namespace(), "requires a matching /proc PID namespace"
    )
    def test_detached_rank_saves_before_agent_is_stopped(self):
        with tempfile.TemporaryDirectory() as d:
            marker = Path(d) / "rank-saved"
            rank = (
                "import signal,time,pathlib\n"
                f"def stop(*args):\n time.sleep(.3)\n pathlib.Path({str(marker)!r}).touch()\n"
                " raise SystemExit(0)\n"
                "signal.signal(signal.SIGTERM,stop)\n"
                "while True:time.sleep(.05)\n"
            )
            agent = (
                "import subprocess,sys\n"
                f"subprocess.run([sys.executable,'-c',{rank!r}],start_new_session=True,check=True)\n"
            )
            worker = (
                f"import subprocess,sys;subprocess.run([sys.executable,'-c',{agent!r}],check=True)"
            )
            result = launcher.launch([sys.executable, "-c", worker], 0.6, grace=2)
            self.assertTrue(result["budget_expired"])
            self.assertTrue(marker.exists())
            self.assertEqual(result["returncode"], 0)
            self.assertEqual(result["forced_kill_groups"], 0)

    @unittest.skipUnless(
        launcher.compatible_proc_namespace(), "requires a matching /proc PID namespace"
    )
    def test_signal_ignoring_detached_rank_is_force_cleaned(self):
        with tempfile.TemporaryDirectory() as d:
            pidfile = Path(d) / "rank-pid"
            rank = (
                "import signal,time,pathlib,os\n"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                "signal.signal(signal.SIGINT,signal.SIG_IGN)\n"
                f"pathlib.Path({str(pidfile)!r}).write_text(str(os.getpid()))\n"
                "time.sleep(10)\n"
            )
            agent = (
                "import subprocess,sys\n"
                f"subprocess.run([sys.executable,'-c',{rank!r}],start_new_session=True)\n"
            )
            result = launcher.launch([sys.executable, "-c", agent], 0.6, grace=0.3)
            self.assertTrue(result["budget_expired"])
            self.assertGreater(result["forced_kill_groups"], 0)
            pid = int(pidfile.read_text())
            info = launcher.process_info(pid)
            self.assertTrue(info is None or info["state"] == "Z")

    def test_failed_worker_cannot_certify_an_existing_complete_report(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            (root / "run").mkdir()
            (root / "run/report.json").write_text('{"status":"complete"}')
            with (
                patch.object(sys, "argv", ["launcher", "--output", d, "--budget-seconds", "60"]),
                patch.object(
                    launcher,
                    "launch",
                    return_value={
                        "returncode": 1,
                        "budget_expired": False,
                        "operator_interrupted": False,
                    },
                ),
                patch.dict(
                    sys.modules,
                    {
                        "trainlab.fullcycle.pipeline": SimpleNamespace(
                            verify_pipeline=lambda *args: self.fail(
                                "must not certify a failed worker"
                            )
                        )
                    },
                ),
            ):
                with self.assertRaises(SystemExit):
                    launcher.main()
            receipt = json.loads((root / "session-receipt.json").read_bytes())
            self.assertEqual(receipt["status"], "FAILED")

    def test_primary_failure_receipt_survives_missing_optional_import(self):
        with tempfile.TemporaryDirectory() as d:
            with (
                patch.object(
                    launcher,
                    "launch",
                    return_value={
                        "returncode": 42,
                        "budget_expired": False,
                        "operator_interrupted": False,
                    },
                ),
                patch.dict(sys.modules, {"trainlab.runner": None}),
            ):
                with self.assertRaises(ModuleNotFoundError):
                    launcher.main(["--output", d, "--budget-seconds", "60"])
            receipt = json.loads((Path(d) / "session-receipt.json").read_bytes())
            self.assertEqual(receipt["status"], "FAILED")
            self.assertEqual(receipt["returncode"], 42)

    def test_prepared_inputs_and_optimizer_resume_are_mutually_exclusive(self):
        with patch.object(launcher, "launch") as start:
            with self.assertRaises(SystemExit):
                launcher.main(["--resume-input", "old", "--prepared-input", "data"])
            self.assertFalse(start.called)

    def test_incompatible_proc_refuses_before_starting_compute(self):
        with (
            patch.object(launcher, "compatible_proc_namespace", return_value=False),
            patch.object(launcher.subprocess, "Popen") as start,
        ):
            with self.assertRaisesRegex(ValueError, "PID namespace"):
                launcher.launch([sys.executable, "-c", "pass"], 0.1)
            self.assertFalse(start.called)

    def test_publish_only_copies_pinned_release_files_and_rejects_tampering(self):
        from forge_data.language import build_release, canonical, digest

        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            source = root / "rows.jsonl"
            row = {"kind": "text", "source_id": "fixture", "group": "x", "text": "Constructed."}
            source.write_bytes(canonical(row) + b"\n")
            spec = {
                "schema": "forge.language-source.v1",
                "source_sha256": digest(source),
                "split_salt": "fixture",
                "sources": {
                    "fixture": {
                        "rights_reviewed": True,
                        "license": "Apache-2.0",
                        "provenance": "constructed test",
                        "source_kind": "CONSTRUCTED",
                    }
                },
            }
            pin = build_release(source, spec, root / "release")
            tokens = root / "tokenizer.json"
            tokens.write_text('{"kind":"byte-v1"}')
            (root / "release/unlisted-link").symlink_to(tokens)
            config = {
                "dataset": {"directory": str(root / "release"), "manifest_sha256": pin},
                "tokenizer": {"artifact_path": str(tokens), "artifact_sha256": digest(tokens)},
            }
            with (
                patch.object(launcher, "RELEASE_SHA256", pin),
                patch.object(launcher, "TOKENIZER_SHA256", digest(tokens)),
            ):
                result = launcher.publish_data(config, root / "persisted")
                self.assertFalse((root / "persisted/release/unlisted-link").exists())
                self.assertEqual(result["dataset"]["manifest_sha256"], pin)
                # A fresh run may reuse only these pinned inputs, never old protocol/state.
                (root / "persisted/run").mkdir()
                (root / "persisted/run/protocol.json").write_text('{"old_run":true}')
                output = root / "fresh-output"
                output.mkdir()
                args = SimpleNamespace(
                    output=output,
                    prepared_input=root / "persisted",
                    resume_input=None,
                    cache=root / "unused-cache",
                    gpus=2,
                )
                with (
                    patch.object(launcher, "hardware"),
                    patch.object(launcher.subprocess, "run") as compute,
                    patch.dict(
                        sys.modules,
                        {
                            "trainlab.fullcycle.pipeline": SimpleNamespace(
                                prepare_configuration=lambda *a: self.fail(
                                    "must reuse prepared inputs"
                                )
                            )
                        },
                    ),
                ):
                    launcher.worker(args)
                    self.assertEqual(compute.call_count, 2)
                    self.assertFalse((output / "run").exists())
                    self.assertFalse(args.cache.exists())
                    training = json.loads((output / "training-config.json").read_bytes())
                    launcher.verify_full_recipe(training, output, 2)
                    compute.reset_mock()
                    (output / "run").mkdir()
                    with self.assertRaisesRegex(ValueError, "fresh run"):
                        launcher.worker(args)
                    self.assertFalse(compute.called)
                (root / "persisted/tokenizer.json").write_text("tampered")
                with self.assertRaisesRegex(ValueError, "tokenizer changed"):
                    launcher.publish_data(config, root / "persisted")

    def test_generated_notebook_is_valid_and_not_misreported_as_executed(self):
        import nbformat

        spec = importlib.util.spec_from_file_location(
            "fullcycle_notebook", EXAMPLES / "build_kaggle.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "job.ipynb"
            receipt = module.build("a" * 40, output)
            notebook = nbformat.read(output, as_version=4)
            nbformat.validate(notebook)
            self.assertEqual(receipt["status"], "STAGED_UNSUBMITTED")
            self.assertFalse(receipt["gpu_executed"])
            self.assertTrue(
                all(c.execution_count is None for c in notebook.cells if c.cell_type == "code")
            )
            parameters = next(c.source for c in notebook.cells if c.cell_type == "code")
            scope = {}
            exec(compile(parameters, "parameters", "exec"), scope)
            calls = []
            scope["runpy"] = SimpleNamespace(
                run_path=lambda path: {"main": lambda args: calls.append((path, args))}
            )
            scope["subprocess"] = SimpleNamespace(run=lambda *a, **kw: self.fail("extra wrapper"))
            handoff = next(
                c.source
                for c in notebook.cells
                if c.cell_type == "code" and "runpy.run_path" in c.source
            )
            exec(compile(handoff, "training handoff", "exec"), scope)
            self.assertEqual(len(calls), 1)
            self.assertIn("--budget-seconds", calls[0][1])
