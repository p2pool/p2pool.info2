This is a rewrite of p2pool.info's backend in Python.

Architecture
----
Data is stored in JSON files in the format that is downloaded by the frontend. The data files are updated by a Python script that should be run every few minutes.


Requirements
----
* A Bitcoin node
* Access to one or more P2Pool nodes (there are many public ones)


Setup
----

Run

    scripts/download

to retrieve a current copy of the data. Then, you should be able
to look at `web/index.html` directly in a browser and everything should
work. Start a webserver hosting the `web/` directory.

Run

    scripts/run

after updating it to point to your Bitcoin node and one or more P2Pool nodes
(find some at http://p2pool-nodes.info/). If some go down, the backend will
use the others. Use cron to run this script at least hourly.
