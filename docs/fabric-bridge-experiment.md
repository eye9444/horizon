# Fabric bridge experiment: Cobblemon preflight

Status: requirements inventory only. **Cobblemon does not run in Horizon.**
This development tool neither loads Java classes nor changes the game runtime.
It is the first reproducible step in a contributor experiment, not Horizon's roadmap.

## Target and project boundary

Horizon targets Minecraft 26.3. This experiment pins Cobblemon Fabric 1.8.4 for
Minecraft 1.21.1, published as [Modrinth version PdOzYHKU](https://modrinth.com/mod/cobblemon/version/PdOzYHKU).
Those are different game APIs; satisfying the loader metadata alone cannot make them compatible.

Horizon maintainers declined unchanged Java mod loading in
[issue #527](https://github.com/horizon-rust/horizon/issues/527).
[CONTRIBUTING.md](../CONTRIBUTING.md) requires Rust for player-facing code and
prohibits deriving implementation from other mods' or loaders' source. This patch
uses published metadata/file formats only. Any JVM runtime experiment belongs in
an explicitly separate fork unless maintainers change that architectural decision.
The existing [native mod port pipeline](modpacks.md) remains a different approach.

## Reproduce

Obtain the pinned Fabric jar from the version page above and keep it outside the
checkout. The tool uses Python's standard library, reads metadata in memory, does
not extract archives, and never executes the mod. It checks declared nested jars
recursively with depth and decompressed-read limits.

```sh
python3 tools/fabric_preflight.py /path/to/Cobblemon-fabric-1.8.4+1.21.1.jar \
  --sha512 8ba3bc7eb0bb6d52309ca339dfc9fb11adcffebe36d183e0a8df7c8e741edbcbc436c60cc877fd2b42aa224670825cf4f55946676b58ecf0e998f9feae2173c2 \
  > /path/outside/checkout/cobblemon-preflight.json
python3 -m unittest tests.test_fabric_preflight
```

The optional digest pin rejects unexpected artifacts before ZIP inspection. A
successful exit means the inventory was read, **not** that dependencies resolve
or the mod is compatible. Malformed/missing declared resources fail the report.
Only schema 1 metadata is supported. Dependency predicates and entrypoints are
preserved, not evaluated. Undeclared nested archives are not traversed. Mixin
counts are declarations, not proof that those patches apply at runtime; plugins
can select additional behavior. Access widener entries are counted, not applied.
No bytecode, mod source or assets appear in the output.

Unlike `horizon-port-pack`'s content census, this tool retains the exact runtime
requirements, entrypoint declarations, side-scoped Mixin configurations and
recursive jar-in-jar dependency metadata for a prospective runtime experiment.
It does not implement a second pack importer or dependency resolver.

## Measured on the pinned artifact

| Requirement | Observed value |
|---|---|
| Mod metadata version | `1.8.4+1.21.1` |
| Minecraft | `1.21.1` |
| Java | `21` |
| Fabric Loader | `>=0.17.2` |
| Fabric API | `>=0.116.6+1.21.1` |
| Top-level class files | 5,970 (excluding nested jars) |
| Common Mixin config | 65 common + 37 client declarations |
| Fabric Mixin config | 7 common + 5 client declarations; config plugin present |
| Access widener | v2, intermediary namespace; 123 entries |
| Direct nested jars | 8 |
| Further jars inside Fabric Language Kotlin | 13 |

The eight direct dependencies bundle Fabric Language Kotlin, Graal SDK, ICU4J,
GraalJS, MongoDB core/sync drivers, Graal regex and Truffle API. Presence does not
prove every library is used on every execution path. Fabric API is an external
required dependency and has not yet been resolved or tested by this experiment.
The Java predicate is copied verbatim; an installed newer JVM is not validation.

## Milestones and evidence required

1. **Inventory (this patch):** pin the artifact, enumerate declared requirements,
   and test the tool using synthetic fixtures. No third-party code fixtures.
2. **Reference environment:** run the original pinned mod in an isolated,
   owned Minecraft 1.21.1 installation with pinned compatible dependencies/JDK.
   Record initialization and a repeatable spawn/capture/save/reload scenario.
3. **Runtime architecture experiment (fork only):** demonstrate one operation
   crossing Java to Rust and back with explicit object lifetime and threading
   rules. This is not Cobblemon initialization. Choose where authoritative world
   state lives before adding wrappers. Do not silently launch vanilla and call it
   Horizon compatibility.
4. **Actual loader initialization:** satisfy real entrypoints and game API calls,
   then explicitly account for each required Mixin and access widener operation.
   Never suppress failed required patches to claim success.
5. **Cobblemon vertical slice:** spawn/render one creature, interact/capture,
   save/reload it; compare outcomes to the reference. Then battles, networking,
   persistence, UI and wider content coverage. No playable claim before this.

An embedded JVM supplies Java execution, not Minecraft 1.21.1 classes or Mixin
injection sites. Rust hooks must actually traverse any Java path whose patches
are expected to affect gameplay. Thin wrappers do not recreate arbitrary method
internals. A version mismatch further requires mapping 1.21.1 semantics onto
26.3 or explicitly retaining a compatible execution path. Feasibility and
performance remain unproven.

Initial local validation used the hash-verified jar above and synthetic unit
tests. No Minecraft/Horizon gameplay was launched; no vanilla parity, rendering,
Fabric initialization or Java/Rust bridge has been demonstrated.
