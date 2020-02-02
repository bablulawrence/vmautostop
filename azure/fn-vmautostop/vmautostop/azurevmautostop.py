from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.monitor import MonitorManagementClient
from azure.mgmt.resource.resources.v2019_07_01 import ResourceManagementClient
from azure.mgmt.subscription import SubscriptionClient
import datetime
import logging
import re
import math
import statistics

TIMESTAMP_TAG = "VM_AUTO_STOP_warning_email_timestamp"
THRESHOLD_TAG = "VM_AUTO_STOP_inactivity_threshold_minutes"
EMAIL_TAG = "VM_AUTO_STOP_warning_email_to"


class Subscription:
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
        subscription_client = SubscriptionClient(credentials)
        subscriptions = subscription_client.subscriptions.list()
        return [cls(credentials, sub["subscription_id"], email_client)
                for sub in [sub_itr.__dict__
                            for sub_itr in subscriptions]]

    def get_virtual_machines(self, default_inactivity_th_mins, post_warning_th_mins,
                             percentage_cpu_stdev_bas_pct, network_out_stdev_bas_pct):
        virtual_machines = list(filter(
            lambda x: THRESHOLD_TAG in x["tags"].keys(),
            [vm.__dict__ for vm in self.resource_client.resources.list(
                filter="resourceType eq 'Microsoft.Compute/virtualMachines'")]
        ))
        vms = []
        for vm in virtual_machines:
            resource_group_name = re.search("resourceGroups/(.*)/providers",
                                            vm["id"]).group(1)
            rg = self.resource_client.resource_groups.get(
                resource_group_name).__dict__
            vms.append(VirtualMachine(self, resource_group_name, rg["tags"],
                                      vm["id"], vm["name"], vm["tags"],
                                      default_inactivity_th_mins, post_warning_th_mins,
                                      percentage_cpu_stdev_bas_pct, network_out_stdev_bas_pct))
        return vms


class VirtualMachine:
    def __init__(self, subscription, resource_group_name, rg_tags,
                 resource_id, name, vm_tags,
                 default_inactivity_th_mins, post_warning_th_mins,
                 percentage_cpu_stdev_bas_pct, network_out_stdev_bas_pct):
        self.subscription = subscription
        self.resource_group_name = resource_group_name
        self.rg_tags = rg_tags
        self.resource_id = resource_id
        self.name = name
        self.vm_tags = vm_tags
        self.inactivity_threshold = self.__get_inactivity_threshold(
            default_inactivity_th_mins)
        self.warning_email_to = self.__get_warning_email_to()
        self.post_warning_th_mins = post_warning_th_mins
        self.percentage_cpu_stdev_bas_pct = percentage_cpu_stdev_bas_pct
        self.network_out_stdev_bas_pct = network_out_stdev_bas_pct

    def __get_inactivity_threshold(self, default_inactivity_th_mins):
        input_threshold = self.vm_tags[THRESHOLD_TAG]
        try:
            threshold = int(input_threshold)
        except ValueError as e:
            logging.exception(
                (f"Invalid inactivity threshold value: {input_threshold}, "
                 f"using default value of {default_inactivity_th_mins} minutes"))
            threshold = default_inactivity_th_mins
        return threshold

    def __get_warning_email_to(self):
        if self.vm_tags and EMAIL_TAG in self.vm_tags.keys():
            return (self.vm_tags[EMAIL_TAG])
        elif self.rg_tags and EMAIL_TAG in self.rg_tags.keys():
            return (self.rg_tags[EMAIL_TAG])
        else:
            return None

    def get_instance_status(self):
        return self.subscription.compute_client.virtual_machines.instance_view(
            self.resource_group_name,
            self.name).statuses[-1].code

    def get_metrics(self, timestamp):
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
        metrics_agg["percent_cpu_stdev_max"] = metrics_agg["percentage_cpu_avg"] * \
            self.percentage_cpu_stdev_bas_pct / 100
        metrics_agg["network_out_stdev_max"] = metrics_agg["network_out_avg"] * \
            self.network_out_stdev_bas_pct / 100
        metrics_agg["percentage_cpu_stdev_pct"] = metrics_agg["percentage_cpu_stdev"] / \
            metrics_agg["percentage_cpu_avg"] * 100
        metrics_agg["network_out_stdev_pct"] = metrics_agg["network_out_stdev"] / \
            metrics_agg["network_out_avg"] * 100
        return metrics_agg

    def __warning_email_timestamp_exits(self):
        return True if self.vm_tags and TIMESTAMP_TAG in self.vm_tags.keys() else False

    def __get_warning_email_timestamp(self):
        if self.__warning_email_timestamp_exits():
            try:
                warning_email_timestamp = datetime.datetime.fromisoformat(
                    self.vm_tags[TIMESTAMP_TAG])
            except ValueError:
                logging.exception(
                    f"Invalid warning email timestamp value: {self.vm_tags[TIMESTAMP_TAG]}")
                warning_email_timestamp = None
        else:
            warning_email_timestamp = None
        return warning_email_timestamp

    def __set_warning_email_timestamp(self, timestamp):
        self.vm_tags[TIMESTAMP_TAG] = timestamp.isoformat()
        self.subscription.resource_client.resources.update_by_id(self.resource_id,
                                                                 "2019-07-01",
                                                                 {'tags': self.vm_tags})

    def __delete_warning_email_timestamp(self):
        del self.vm_tags[TIMESTAMP_TAG]
        self.subscription.resource_client.resources.update_by_id(self.resource_id,
                                                                 "2019-07-01",
                                                                 {'tags': self.vm_tags})

    def __send_warning(self, timestamp):
        subject = f"VM Auto Stop Warning: {timestamp.strftime('%Y-%m-%dT%H:%M:%SZ')} - {self.name}"
        body = (f"Virtual Machine - <strong > {self.resource_id} < /strong > is inactive "
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
        action = "None"
        instance_status = self.get_instance_status()
        metrics = self.get_metrics(timestamp)
        if instance_status == "PowerState/running":
            if metrics["percentage_cpu_stdev"] <= metrics["percent_cpu_stdev_max"] \
                    and metrics["network_out_stdev"] <= metrics["network_out_stdev_max"]:
                warning_email_timestamp = self.__get_warning_email_timestamp()
                if warning_email_timestamp == None:
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
