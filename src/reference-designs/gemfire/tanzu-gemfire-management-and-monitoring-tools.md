# Tanzu GemFire Management and Monitoring Tools

Internally, Tanzu GemFire exposes its management and monitoring surface through Java MBeans, specifically MXBeans, that any JMX-compliant client can consume. On top of this foundation, GemFire provides several tools: the `gfsh` command-line interface, which is the primary administrative tool, Tanzu GemFire Management Console , which is a browser-based operations console, a Prometheus metrics endpoint on each member, a management REST API, and out-of-the-box integration for observability.

## <a id="gfsh-tool"></a> `gfsh` Command-Line Tool

The GemFire Shell (`gfsh`) is the recommended command-line interface for configuring, managing, and monitoring a cluster. `gfsh` lets you:

- Start and stop locators and cache servers.

- Create, alter, or destroy regions.

- Deploy and manage application JARs.

- Execute user-defined functions.

- Manage disk stores and perform data import and export.

- Monitor members and system metrics.

- Save and manage shared cluster configurations.

You can run `gfsh` as an interactive shell, or you can invoke `gfsh` from the OS command line, and `gfsh` supports scripting for automation. `gfsh` can manage a remote cluster over HTTP or HTTPS, or connect to a JMX Manager member for JMX-based commands. With shared cluster configuration, `gfsh` maintains reusable settings that locators store and synchronize across the cluster, for example, `cluster.xml` and `cluster.properties`. More information:

- [Running `gfsh` Commands on the OS Command Line](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-3/gf/tools_modules-gfsh-os_command_line_execution.html)

- [Using `gfsh` to Manage a Remote Cluster Over HTTP or HTTPS](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-3/gf/configuring-cluster_config-gfsh_remote.html)

- [Creating and Running `gfsh` Command Scripts](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire/10-3/gf/tools_modules-gfsh-command_scripting.html)

## <a id="management-console"></a> Tanzu GemFire Management Console

Tanzu GemFire Management Console is a browser-based console that streamlines day-to-day operations and provides visual insight across your GemFire estate. Tanzu GemFire Management Console is delivered as a standalone application, either a JAR file that requires JDK 11, 17, or 21, or an OCI container image, and Tanzu GemFire Management Console runs alongside your clusters rather than as part of them. Tanzu GemFire Management Console is not a `gfsh` command. Tanzu GemFire Management Console can manage an entire fleet of clusters, including multi-site (WAN) topologies, from a single interface.

### <a id="gmc-operations"></a> Operations and management (write) capabilities

- Monitor and manage multiple clusters, with a real-time multi-site topology view.

- Create and configure regions, deploy or remove JARs, and manage disk stores.

- Execute functions and manage WAN gateway senders and receivers.

- Explore and query data with the built-in Data Explorer, which lets you run OQL, inspect entries, and copy data between clusters.

- Run commands through a built-in web-based `gfsh`.

- Search and download member logs. See the note under [Logging](#gmc-logging) below.

### <a id="gmc-monitoring"></a> Monitoring and observability (Tanzu GemFire 10.2 and 10.3)

Tanzu GemFire Management Console drives its monitoring dashboards directly from Prometheus rather than proxying the metrics. The relevant 10.2 and 10.3 behavior:

- **Metrics source.** Each member, locator or server, exposes its Prometheus metrics at the `/metrics` path on its HTTP service port, `http-service-port`, which defaults to 7070. This endpoint replaced the earlier per-member "metrics port" model used in 10.1 and earlier. Metric names are the GemFire statistics prefixed with `gemfire_`, for example, `gemfire_gets`.

- **Enablement.** The member serves the endpoint only when its HTTP service is running. Locators enable this through `enable-management-rest-service`, which defaults to `true`. Servers enable this through `--start-rest-api`, which defaults to `false`, so you must enable this explicitly on servers. You control per-member emission with `gemfire.prometheus.metrics.emission`, which accepts `Default`, `All`, or `None`.

- **Prometheus, embedded or external.** Tanzu GemFire Management Console can auto-start an embedded Prometheus server, available only for OVA and OCI distributions, or connect to an external, organization-managed Prometheus instance. When you use Tanzu GemFire Management Console for monitoring and you secure the member metrics endpoints, using a security manager, TLS, or both, Tanzu GemFire Management Console acts as a proxy for external Prometheus scraping requests to satisfy these security and connection constraints.

- **Real-time-only mode.** You can also view metrics directly in Tanzu GemFire Management Console without a Prometheus server. Tanzu GemFire Management Console retains up to 60 minutes of recent data in this mode. This mode is useful for lightweight, live visibility.

- **Retention and dashboards.** With Prometheus, Tanzu GemFire Management Console presents a historical window of up to seven days, which is the embedded default. Prometheus is the time-series store, so you can attach Grafana to the same Prometheus for custom, enterprise-wide dashboards.

- **Graphs.** The Monitoring tab organizes metrics into three categories. The Data category covers throughput and latencies including P95 and P99, cache hit ratio, queries, and async event queues. The Cluster category covers memory, disk utilization, CPU, and client connections. The WAN Gateway category covers receiver throughput and sender queues.

Tanzu GemFire Management Console is ideal for both routine operations and troubleshooting, providing an intuitive experience for administrators. For more information on Tanzu GemFire Management Console, see [Tanzu GemFire Management Console](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire-management-console/1-4/gf-mc/index.html)

### <a id="gmc-logging"></a> Logging

Tanzu GemFire Management Console's Logs tab lets you view and download logs and statistics for the locators and servers of a connected cluster, with filtering by date range and log level. This tab is intended for development and troubleshooting, and this tab may be insufficient for trailing production logs. The logs themselves live on the member nodes. Tanzu GemFire Management Console reads the logs on demand rather than aggregating or retaining the logs. For production, forward member logs to an enterprise logging platform.

### <a id="gmc-auth"></a> Authentication modes

Tanzu GemFire Management Console supports NONE, meaning Developer Mode, OAuth2, LDAP, including LDAP over TLS/SSL, and SAML for multi-user access.  

For more information on Tanzu GemFire Management Console, see the [Product Documentation](https://techdocs.broadcom.com/us/en/vmware-tanzu/data-solutions/tanzu-gemfire-management-console/1-4/gf-mc/index.html)

