from azure.mgmt.resource.subscriptions import SubscriptionClient
from azure.mgmt.resource.resources.v2019_07_01 import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
import datetime
import logging
import re
import math
import statistics

PARAMS_TAG = "VM_AUTO_STOP_PARAMS"
TIMESTAMP_TAG = "VM_AUTO_STOP_EMAIL_TIMESTAMP"


class Subscription:
    """
    This class provides functionality to get necessary details from azure subscriptions.
    """

    def __init__(self, credentials, subscription_id, email_client):
        self.subscription_id = subscription_id
        self.resource_client = ResourceManagementClient(credentials,
                                                        subscription_id)
        self.monitor_client = MonitorManagementClient(credentials,
                                                      subscription_id)

        self.compute_client = ComputeManagementClient(credentials,
                                                      subscription_id)
        self.email_client = email_client

    @classmethod
    def get_subscriptions(cls, credentials, email_client):
        """
        Gets the list of subscriptions that app has access to.         
        """
        subscription_client = SubscriptionClient(credentials)
        subscriptions = subscription_client.subscriptions.list()
        return [cls(credentials, sub["subscription_id"], email_client)
                for sub in [sub_itr.__dict__
                            for sub_itr in subscriptions]]

    def __extract_params(self, tag_value):
        """
        Extracts parameters and values from the parameter tag.         
        """
        params = [param.strip().split("=")
                  for param in tag_value.strip().split(";")]
        tags = {}
        for p in params:
            tags[p[0]] = p[1]
        return tags

    def get_virtual_machines(self, default_inactivity_th_mins, default_post_warning_th_mins,
                             default_percentage_cpu_stdev_bas_pct, default_network_out_stdev_bas_pct):
        """
        Gets the resource details for all virtual machines in the subscription.         
        """
        virtual_machines = [vm.__dict__ for vm in self.resource_client.resources.list(
            filter="resourceType eq 'Microsoft.Compute/virtualMachines'")]
        vms = []
        for vm in virtual_machines:
            resource_group_name = re.search("resourceGroups/(.*)/providers",
                                            vm["id"]).group(1)
            rg = self.resource_client.resource_groups.get(
                resource_group_name).__dict__
            params = {}
            if rg["tags"] is not None and PARAMS_TAG in rg["tags"].keys():
                params.update(self.__extract_params(
                    rg["tags"][PARAMS_TAG]))
            if vm["tags"] is not None and PARAMS_TAG in vm["tags"].keys():
                params.update(self.__extract_params(
                    vm["tags"][PARAMS_TAG]))
            if params is not None and params["AUTO_STOP"] is not None:
                if params["AUTO_STOP"] == "Y" or params["AUTO_STOP"] == "YES":
                    vms.append(VirtualMachine(self, resource_group_name,
                                              vm["id"], vm["name"], vm["tags"], params,
                                              default_inactivity_th_mins, default_post_warning_th_mins,
                                              default_percentage_cpu_stdev_bas_pct, default_network_out_stdev_bas_pct))

        return vms


class VirtualMachine:
    """
    This class provides functionality to read VM status, get metrics, send notification and stop VM.
    """

    def __init__(self, subscription, resource_group_name,
                 resource_id, name, tags, params,
                 default_inactivity_th_mins, default_post_warning_th_mins,
                 default_percentage_cpu_stdev_bas_pct, default_network_out_stdev_bas_pct):
        self.subscription = subscription
        self.resource_group_name = resource_group_name
        self.resource_id = resource_id
        self.name = name
        self.tags = tags

        if "WARN_EMAIL_TO" in params.keys():
            self.warning_email_to = params["WARN_EMAIL_TO"]
        else:
            self.warning_email_to = None

        if "INACTIVITY_TH_MIN" in params.keys():
            try:
                self.inactivity_threshold = int(params["INACTIVITY_TH_MIN"])
            except ValueError as e:
                logging.exception(
                    (f"Invalid inactivity threshold value: {params['INACTIVITY_TH_MIN']}, "
                     f"using default value of {default_inactivity_th_mins} minutes"))
                self.inactivity_threshold = default_inactivity_th_mins
        else:
            self.inactivity_threshold = default_inactivity_th_mins

        if "POST_WARN_TH_MINS" in params.keys():
            try:
                self.post_warning_th_mins = int(params['POST_WARN_TH_MINS'])
            except ValueError as e:
                logging.exception(
                    (f"Invalid post warning threshold value: {params['POST_WARN_TH_MINS']}, "
                     f"using default value of {default_post_warning_th_mins} minutes"))
                self.post_warning_th_mins = default_post_warning_th_mins
        else:
            self.post_warning_th_mins = default_post_warning_th_mins

        if "CPU_STDEV_BAS_PCT" in params.keys():
            try:
                self.percentage_cpu_stdev_bas_pct = float(
                    params["CPU_STDEV_BAS_PCT"])
            except ValueError as e:
                logging.exception(
                    (f"Invalid Percentage CPU standard deviation base percentage: {params['CPU_STDEV_BAS_PCT']}, "
                     f"using default value of {default_percentage_cpu_stdev_bas_pct} minutes"))
                self.percentage_cpu_stdev_bas_pct = default_percentage_cpu_stdev_bas_pct
        else:
            self.percentage_cpu_stdev_bas_pct = default_percentage_cpu_stdev_bas_pct

        if "NETW_STDEV_BAS_PCT" in params.keys():
            try:
                self.network_out_stdev_bas_pct = float(
                    params["NETW_STDEV_BAS_PCT"])
            except ValueError as e:
                logging.exception(
                    (f"Invalid Network Out standard deviation base percentage: {params['NETW_STDEV_BAS_PCT']}, "
                     f"using default value of {default_network_out_stdev_bas_pct} minutes"))
                self.network_out_stdev_bas_pct = default_network_out_stdev_bas_pct
        else:
            self.network_out_stdev_bas_pct = default_network_out_stdev_bas_pct

    def get_instance_status(self):
        """
        Gets the status on the VM.
        """
        return self.subscription.compute_client.virtual_machines.instance_view(
            self.resource_group_name,
            self.name).statuses[-1].code

    def get_metrics(self, timestamp):
        """
        Gets the metrics values for the VM and calculates aggregate metrics.
        """
        adj_curr_time = timestamp - datetime.timedelta(minutes=3)
        start_time = (adj_curr_time - datetime.timedelta(minutes=self.inactivity_threshold)
                      ).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_time = adj_curr_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        value = self.subscription.monitor_client.metrics.list(
            self.resource_id,
            timespan="{}/{}".format(start_time, end_time),
            metricnames="Percentage CPU,Network Out",
            aggregation="Total"
        ).value
        metrics = {"Percentage CPU": [],
                   "Network Out": []}
        for i in value:
            data = i.timeseries[0].data
            for j in data:
                try:
                    metrics[i.name.value].append(float(j.total))
                except TypeError as e:
                    metrics[i.name.value].append(math.inf)
        metrics_agg = {
            "percentage_cpu_values": metrics["Percentage CPU"],
            "network_out_values": metrics["Network Out"],
            "percentage_cpu_avg": statistics.mean(metrics["Percentage CPU"]),
            "percentage_cpu_stdev": statistics.stdev(metrics["Percentage CPU"]),
            "network_out_avg": statistics.mean(metrics["Network Out"]),
            "network_out_stdev": statistics.stdev(metrics["Network Out"])
        }
        metrics_agg["percent_cpu_stdev_max"] = (metrics_agg["percentage_cpu_avg"] *
                                                self.percentage_cpu_stdev_bas_pct / 100)
        metrics_agg["network_out_stdev_max"] = (metrics_agg["network_out_avg"] *
                                                self.network_out_stdev_bas_pct / 100)
        metrics_agg["percentage_cpu_stdev_pct"] = (metrics_agg["percentage_cpu_stdev"] /
                                                   metrics_agg["percentage_cpu_avg"] * 100)
        metrics_agg["network_out_stdev_pct"] = (metrics_agg["network_out_stdev"] /
                                                metrics_agg["network_out_avg"] * 100)
        return metrics_agg

    def __warning_email_timestamp_exits(self):
        """
        Checks whether the warning email timestamp tag exists in the VM.
        """
        return True if self.tags and TIMESTAMP_TAG in self.tags.keys() else False

    def __get_warning_email_timestamp(self):
        """
        Gets the value of the warning email timestamp.
        """
        if self.__warning_email_timestamp_exits():
            try:
                warning_email_timestamp = datetime.datetime.fromisoformat(
                    self.tags[TIMESTAMP_TAG])
            except ValueError:
                logging.exception(
                    f"Invalid warning email timestamp value: {self.tags[TIMESTAMP_TAG]}")
                warning_email_timestamp = None
        else:
            warning_email_timestamp = None
        return warning_email_timestamp

    def __set_warning_email_timestamp(self, timestamp):
        """
        Sets the warning email timestamp.
        """
        self.tags[TIMESTAMP_TAG] = timestamp.isoformat()
        self.subscription.resource_client.resources.update_by_id(self.resource_id,
                                                                 "2019-07-01",
                                                                 {'tags': self.tags})

    def __delete_warning_email_timestamp(self):
        """
        Deletes the warning email timestamp.
        """
        del self.tags[TIMESTAMP_TAG]
        self.subscription.resource_client.resources.update_by_id(self.resource_id,
                                                                 "2019-07-01",
                                                                 {'tags': self.tags})

    def __send_warning(self, timestamp):
        """
        Sends the warning email.
        """
        subject = f"VM Auto Stop Warning: {timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')} - {self.name}"
        body = (f"Virtual Machine - <strong> {self.resource_id} </strong> is inactive "
                f"and will be stopped in {self.post_warning_th_mins} mins")
        try:
            self.subscription.email_client.send_message(
                subject, body, self.warning_email_to)
            return True
        except Exception as e:
            logging.exception(
                f"Send warning email failed: {str(e)}")
            return False

    def stop(self, timestamp):
        """
        Stops the VM if the inactivity criteria is met.
        """
        action = "None"
        instance_status = self.get_instance_status()
        metrics = self.get_metrics(timestamp)
        if instance_status == "PowerState/running":
            if (metrics["percentage_cpu_stdev"] <= metrics["percent_cpu_stdev_max"]
                    and metrics["network_out_stdev"] <= metrics["network_out_stdev_max"]):
                warning_email_timestamp = self.__get_warning_email_timestamp()
                if warning_email_timestamp is None:
                    if self.__send_warning(timestamp):
                        self.__set_warning_email_timestamp(timestamp)
                        action = "Warning sent"
                    else:
                        action = "Warning failed"
                elif divmod((timestamp - warning_email_timestamp).seconds, 60)[0] >= self.post_warning_th_mins:
                    action = "Stopping"
                    self.__delete_warning_email_timestamp()
                    async_vm_deallocate = self.subscription.compute_client.virtual_machines.deallocate(
                        self.resource_group_name,
                        self.name)
                    # async_vm_deallocate.wait()
            else:
                if self.__warning_email_timestamp_exits():
                    self.__delete_warning_email_timestamp()
        return {"timestamp": timestamp.isoformat(),
                "resource_id": self.resource_id,
                "instance_status": instance_status,
                "inactivity_threshold": self.inactivity_threshold,
                "warning_email_to": self.warning_email_to or self.subscription.email_client.get_email_to(),
                "action": action,
                "metrics": metrics}
