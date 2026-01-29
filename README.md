# EvidenT: An Evidence-Preserving Framework for Iterative System-Level Package Repair

## 👋 Overview
EvidenT is an automated repair framework for **system-level package builds**.

<p align="center">
  <img src="assets/framework.png" width="850">
</p>

It treats package repair as an evidence-driven and iterative workflow that coordinates:

- anomaly-focused log condensation,
- dependency and recipe-level constraint extraction,
- historical repair case retrieval,
- ISA-specific knowledge contextualization,
- and build-based validation through the Open Build Service (OBS).

EvidenT is implemented on top of the **Model Context Protocol (MCP)**, enabling modular tool orchestration across analysis, repair, and validation phases.


## 🔍 Repository Structure

```text
aiops_pro/
├── client.py                  # Iterative repair controller (repair loop entry)
├── server.py                  # MCP tool server exposing repair components
│
├── config/
│   └── paths.yaml             # Local paths + OBS configuration
│
├── knowledge_base/
│   ├── history_solution.csv        # Historical repair cases mined from GitHub
│   └── risc_v_knowledge_base.csv   # ISA-specific Knowledge Context (RISC-V)
│
├── temp_workspace/            # Temporary workspaces for package repair runs
│
├── tools/
│   ├── analysis_and_repair/   # Failure analysis + localization components
│   │   ├── anomaly_detection.py      # Anomaly-focused log condensation
│   │   ├── dependency_constrain.py   # Dependency Constraints from build recipes
│   │   ├── historical_case.py        # Historical fix retrieval
│   │   ├── arch_know_search.py       # ISA-specific Knowledge Context search
│   │   └── localize_structure.py     # Workspace structure localization
│   │
│   └── validation/            # Build-based validation components
│       ├── upload_files.py    # Upload repaired packages to OBS
│       └── check_build_res.py # Query OBS build status + fetch updated logs
│
└── utils/prompts/
    ├── merged_prompt_loop.txt # Dynamic prompt template used in EvidenT
    └── prompt_bare_LLM.txt    # Baseline prompt (w/o orchestration)
```

## 🚀 Quick Start
### Activate the virtual environment
```
uv init
uv add venv
source .venv/bin/activate
uv pip install -r requirements.txt
```

### Run the client and rebuild packages
```
python client.py
```

## 🧩 Build Repair Results
The dataset is available at [OSF](https://osf.io/7g4ux/files/osfstorage?view_only=b18895dde06b4d5d8054df0616e5fad4), which contains the build results of 219 RISC-V packages (riscv_failed_repair.zip, riscv_succeed_repair.zip).

In total, 219 packages were evaluated. Among them:
118 packages were successfully repaired (success) by EvidenT, the overall success rate is 53.88%.

The detail of repair results is as follows:

| package                               | repair result   |
|:--------------------------------------|:----------------|
| pixelorama                            | ❌ failed          |
| python-ly                             | ✅ success         |
| keylightctl                           | ❌ failed          |
| trng                                  | ✅ success         |
| postquantumcryptoengine               | ❌ failed          |
| rpmconf                               | ❌ failed          |
| password-store                        | ✅ success         |
| vdt                                   | ✅ success         |
| velero-plugin-for-aws                 | ✅ success         |
| kubectl-browse-pvc                    | ✅ success         |
| apache2-mod_wsgi                      | ✅ success         |
| python-guessit                        | ✅ success         |
| babeltrace2                           | ✅ success         |
| lpcnet                                | ✅ success         |
| kubectl-directpv                      | ✅ success         |
| bazel-rules-go                        | ✅ success         |
| python-libusb1                        | ✅ success         |
| python-pyp                            | ❌ failed          |
| python-dqsegdb                        | ✅ success         |
| LaTeXML                               | ❌ failed          |
| python-BitVector                      | ✅ success         |
| ansible-cmdb                          | ✅ success         |
| python-flake8-comprehensions          | ✅ success         |
| velero-plugin-for-csi                 | ❌ failed          |
| nlopt                                 | ❌ failed         |
| monitoring-plugins-http_json          | ✅ success         |
| kubectl-validate                      | ❌ failed          |
| kubie                                 | ✅ success         |
| linode-cli                            | ✅ success         |
| python-safetensors                    | ✅ success         |
| python-WSME                           | ❌ failed          |
| python-xsge_lighting                  | ✅ success         |
| python-pytest-system-statistics       | ✅ success         |
| perl-local-lib                        | ✅ success         |
| lib2geom                              | ❌ failed          |
| perl-gettext                          | ✅ success         |
| python-subst                          | ✅ success         |
| python-geomdl                         | ❌ failed          |
| stb                                   | ❌ failed          |
| python-jdatetime                      | ❌ failed          |
| python-traits                         | ✅ success         |
| ansible-terraform-inventory           | ✅ success         |
| python-pytest-subprocess              | ✅ success         |
| gopass                                | ❌ failed          |
| cjose                                 | ✅ success         |
| python-hid-parser                     | ❌ failed          |
| golly                                 | ❌ failed          |
| opensurge                             | ❌ failed          |
| python-antlr4-python3-runtime         | ✅ success         |
| mypaint                               | ✅ success         |
| rubygem-slim                          | ✅ success         |
| python-pyscard                        | ❌ failed          |
| python-safe-netrc                     | ✅ success         |
| dnsproxy                              | ✅ success         |
| python-stomper                        | ✅ success         |
| nginx-module-njs                      | ✅ success         |
| python-djangorestframework-camel-case | ✅ success         |
| evemu                                 | ✅ success         |
| python-model-bakery                   | ✅ success         |
| rbenv                                 | ✅ success         |
| just                                  | ✅ success         |
| python-line_profiler                  | ✅ success         |
| mcabber                               | ✅ success         |
| rustscan                              | ❌ failed          |
| rtl8188gu                             | ❌ failed          |
| python-pyaes                          | ❌ failed          |
| python-openstacksdk                   | ❌ failed          |
| NetworkManager-fortisslvpn            | ✅ success         |
| python-skyfield                       | ✅ success         |
| python-python-louvain                 | ✅ success         |
| sleef                                 | ❌ failed          |
| cage                                  | ❌ failed          |
| python-odorik                         | ❌ failed          |
| python-pylink-square                  | ❌ failed          |
| python-npTDMS                         | ✅ success         |
| python-flufl.bounce                   | ✅ success         |
| python-Js2Py                          | ❌ failed          |
| python-mrcz                           | ✅ success         |
| python-django-silk                    | ❌ failed          |
| python-autopage                       | ❌ failed          |
| python-astunparse                     | ✅ success         |
| python-qsymm                          | ✅ success         |
| python-pytools                        | ❌ failed          |
| python-pytils                         | ✅ success         |
| pocl                                  | ❌ failed          |
| rubygem-gpgme                         | ❌ failed          |
| hyprpaper                             | ❌ failed          |
| libsigscan                            | ❌ failed          |
| python-pyeapi                         | ✅ success         |
| python-oslo.i18n                      | ✅ success         |
| python-expiringdict                   | ❌ failed          |
| python-urwid-readline                 | ✅ success         |
| python-jellyfish                      | ❌ failed          |
| python-http-parser                    | ✅ success         |
| hypridle                              | ❌ failed          |
| libcec                                | ✅ success         |
| python-visvis                         | ✅ success         |
| librseq                               | ✅ success         |
| libluksde                             | ❌ failed          |
| python-autoflake                      | ✅ success         |
| python-ligotimegps                    | ✅ success         |
| gasket-driver                         | ❌ failed          |
| perl-SDL                              | ❌ failed          |
| v4l2loopback                          | ✅ success          |
| python-Flask-Migrate                  | ✅ success         |
| ufw                                   | ❌ failed          |
| gthumb                                | ✅ success         |
| libnvme                               | ❌ failed          |
| python-zxcvbn-rs-py                   | ❌ failed          |
| python-slimit                         | ❌ failed          |
| python-opt-einsum                     | ✅ success         |
| python-http-ece                       | ✅ success         |
| python-django-tastypie                | ❌ failed          |
| python-simplegeneric                  | ❌ failed          |
| perl-MouseX-Getopt                    | ✅ success         |
| tectonic                              | ❌ failed          |
| python-django-contrib-comments        | ✅ success         |
| jrnl                                  | ❌ failed          |
| python-cluster                        | ❌ failed          |
| libvsmbr                              | ❌ failed          |
| python-junos-eznc                     | ❌ failed          |
| python-mediafile                      | ❌ failed          |
| esc                                   | ✅ success         |
| gpa                                   | ❌ failed          |
| python-rencode                        | ❌ failed          |
| python-aenum                          | ✅ success         |
| perl-Prima                            | ✅ success         |
| python-pscript                        | ❌ failed          |
| python-espeak                         | ❌ failed          |
| python-slixmpp                        | ❌ failed          |
| wl-screenrec                          | ❌ failed         |
| python-wirerope                       | ❌ failed          |
| rtla                                  | ❌ failed          |
| perl-SGML-Parser-OpenSP               | ❌ failed          |
| python-lazyarray                      | ✅ success         |
| python-anyio3                         | ❌ failed          |
| gource                                | ❌ failed          |
| python-pyroma                         | ❌ failed          |
| libgovirt                             | ✅ success         |
| python-fb-re2                         | ✅ success         |
| python-oslo.policy                    | ✅ success         |
| python-acitoolkit                     | ✅ success         |
| python-pytaglib                       | ❌ failed          |
| python-openwrt-luci-rpc               | ❌ failed          |
| howl                                  | ❌ failed          |
| python-napalm                         | ✅ success         |
| python-libusbsio                      | ✅ success         |
| python-pydub                          | ✅ success         |
| expat                                 | ❌ failed          |
| python-txaio                          | ✅ success         |
| mhvtl                                 | ✅ success         |
| hobbits                               | ✅ success         |
| python-boltons                        | ✅ success         |
| python-python-pptx                    | ✅ success         |
| python-django-debug-toolbar           | ❌ failed          |
| libcreg                               | ❌ failed          |
| python-pegen                          | ✅ success         |
| python-kafka-python                   | ❌ failed          |
| element-web                           | ✅ success         |
| python-numcodecs                      | ✅ success         |
| pgvector_postgresql17                 | ❌ failed          |
| python-yappi                          | ❌ failed          |
| python-reconfigure                    | ✅ success         |
| openscap-report                       | ✅ success         |
| python-pandas-datareader              | ❌ failed          |
| cloudflared                           | ❌ failed          |
| orthanc-mysql                         | ✅ success         |
| python-aioquic                        | ✅ success         |
| python-django-perf-rec                | ✅ success         |
| libSavitar                            | ❌ failed          |
| python-dynaconf                       | ❌ failed          |
| python-exiv2                          | ❌ failed          |
| python-pulsectl                       | ✅ success         |
| clazy                                 | ❌ failed         |
| python-smart-open                     | ✅ success         |
| pulseview                             | ❌ failed          |
| python-web.py                         | ❌ failed          |
| python-PyKMIP                         | ❌ failed          |
| klp-build                             | ✅ success         |
| ncmpcpp                               | ❌ failed          |
| xpadneo                               | ❌ failed          |
| python-django-sortedm2m               | ✅ success         |
| python-pprintpp                       | ❌ failed          |
| python-pyshould                       | ✅ success         |
| redshift                              | ❌ failed          |
| coturn                                | ❌ failed          |
| python-augeas                         | ✅ success         |
| tiny                                  | ❌ failed          |
| hotspot                               | ❌ failed          |
| python-pyct                           | ✅ success         |
| bird                                  | ✅ success         |
| rspamd                                | ❌ failed          |
| python-chroma-hnswlib                 | ✅ success         |
| reproc                                | ✅ success         |
| python-psychtoolbox                   | ✅ success         |
| WindowMaker                           | ❌ failed          |
| libfsext                              | ✅ success         |
| python-unittest-xml-reporting         | ✅ success         |
| med-tools                             | ❌ failed          |
| python-tiktoken                       | ✅ success         |
| python-sfs                            | ❌ failed          |
| python-whatever                       | ✅ success         |
| python-opencensus-ext-azure           | ❌ failed          |
| python-azure-devops                   | ❌ failed          |
| liboqs                                | ✅ success         |
| python-cpplint                        | ❌ failed          |
| guake                                 | ✅ success         |
| python-encore                         | ❌ failed          |
| python-devpi-common                   | ✅ success         |
| baresip                               | ✅ success         |
| ubridge                               | ✅ success         |
| python-requests-hawk                  | ❌ failed          |
| python-xkcdpass                       | ✅ success         |
| lalmetaio                             | ✅ success         |
| python-rollbar                        | ✅ success         |
| stalld                                | ❌ failed          |
| marisa                                | ❌ failed          |
| highway                               | ✅ success         |
| clusterssh                            | ✅ success         |
