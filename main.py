import os
import ldclient
from ldclient import Context
from ldclient.config import Config
from ldclient.hook import Hook, Metadata
from threading import Event
from halo import Halo
from firehose_sender import FirehoseSender
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


# Set sdk_key to your LaunchDarkly SDK key.
sdk_key = os.getenv('LAUNCHDARKLY_SDK_KEY', 'sdk-key-placeholder')

# Set feature_flag_key to the feature flag key you want to evaluate.
feature_flag_key = os.getenv('LAUNCHDARKLY_FLAG_KEY', 'default-flag-key')

# Set this environment variable to skip the loop process and evaluate the flag
# a single time.
ci = os.getenv('CI')


def show_evaluation_result(key: str, value: bool):
    print()
    print(f"*** The {key} feature flag evaluates to {value}")

    if value:
        show_banner()


def show_banner():
    print()
    print("        ██       ")
    print("          ██     ")
    print("      ████████   ")
    print("         ███████ ")
    print("██ LAUNCHDARKLY █")
    print("         ███████ ")
    print("      ████████   ")
    print("          ██     ")
    print("        ██       ")
    print()


class FlagValueChangeListener:
    def flag_value_change_listener(self, flag_change):
        show_evaluation_result(flag_change.key, flag_change.new_value)

class FlagEvaluationHook(Hook):
    def __init__(self):
        # Initialize Firehose sender
        try:
            self.firehose_sender = FirehoseSender()
            print("Firehose sender initialized successfully")
        except Exception as e:
            print(f"Failed to initialize Firehose sender: {e}")
            self.firehose_sender = None
    
    @property
    def metadata(self) -> Metadata:
        return Metadata(name="flag-evaluation-hook")

    def after_evaluation(self, evaluation_context, data, evaluation_detail):
        """
        Hook method called after flag evaluation.
        Sends experiment data to Firehose if user is in an experiment.
        """
        print(f"--------------------------------")
        print(f"HOOK FIRED:")
        
        # # Debug: Print all parameter contents
        # print(f"evaluation_context type: {type(evaluation_context)}")
        # print(f"evaluation_context content: {evaluation_context}")
        # print(f"data type: {type(data)}")
        # print(f"data content: {data}")
        # print(f"evaluation_detail type: {type(evaluation_detail)}")
        # print(f"evaluation_detail content: {evaluation_detail}")
        
        # Check if the user is in an experiment looking at the evaluation_detail > reason > inExperiment
        if (evaluation_detail.reason and 
            'inExperiment' in evaluation_detail.reason and 
            evaluation_detail.reason['inExperiment']):
            
            print(f"Experiment detected for flag {evaluation_context.key} - sending to Firehose")
            # Send experiment event to Firehose
            if self.firehose_sender:
                success = self.firehose_sender.send_experiment_event(evaluation_context, evaluation_detail)
                if success:
                    print(f"Successfully sent experiment event to Firehose")
                else:
                    print(f"Failed to send experiment event to Firehose")
            else:
                print(f"Firehose sender not available - skipping event send")
        else:
            print(f"User is NOT in an experiment for flag {evaluation_context.key}!")
        print(f"--------------------------------")
        
        return data

example_analytics_hook = FlagEvaluationHook()

if __name__ == "__main__":
    if not sdk_key:
        print("*** Please set the LAUNCHDARKLY_SDK_KEY env first")
        exit()
    if not feature_flag_key:
        print("*** Please set the LAUNCHDARKLY_FLAG_KEY env first")
        exit()

    ldclient.set_config(Config(sdk_key, hooks=[example_analytics_hook]))

    if not ldclient.get().is_initialized():
        print("*** SDK failed to initialize. Please check your internet connection and SDK credential for any typo.")
        exit()

    print("*** SDK successfully initialized")

    # Set up the evaluation context. This context should appear on your
    # LaunchDarkly contexts dashboard soon after you run the demo.
    context = \
        Context.builder('testing-user-v3').kind('user').set('tier', 'silver').build()

    flag_value = ldclient.get().variation_detail(feature_flag_key, context, "Control")
    # fun_flag_value = ldclient.get().variation_detail("fun-flag-2", context, False)
    # show_evaluation_result(feature_flag_key, flag_value)

    if ci is None:
        change_listener = FlagValueChangeListener()
        # listener = ldclient.get().flag_tracker \
            # .add_flag_value_change_listener(feature_flag_key, context, change_listener.flag_value_change_listener)

        with Halo(text='Waiting for changes', spinner='dots'):
            try:
                Event().wait()
            except KeyboardInterrupt:
                pass
