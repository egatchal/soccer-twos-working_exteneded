import matplotlib.pyplot as plt
import pandas as pd
import numpy as np
import torch
import time
import os

plt.style.use('dark_background')


class MAPPOTrainer:
    """
    A class for the implementation and utilization of the training process
    steps for the Multi-Agent Proximal Policy Optimization algorithm.

    Attributes:
        env: A UnityEnvironment used for Agent evaluation and training.
        agents: Agent objects being trained in env.
        score_window_size: Integer window size used in order to gather
            mean score to evaluate environment solution.
        max_epsiode_length: An integer for maximum number of timesteps per
            episode.
        update_frequency: An integer designating the step frequency of
            updating target network parameters.
        save_dir: Path designating directory to save resulting files.
    """

    def __init__(self, env, agents, score_window_size, max_episode_length,
                 update_frequency, save_dir):
        """Initializes MAPPOTrainer attributes."""

        # Initialize relevant variables for training.
        self.env = env
        self.agents = agents
        self.score_window_size = score_window_size
        self.max_episode_length = max_episode_length
        self.update_frequency = update_frequency
        self.save_dir = save_dir
        self.score_history = []
        self.episode_length_history = []
        self.timestep = 0
        self.i_episode = 0

    def reset_env(self):
        self.env.reset()
        states, rewards, done, info = self.env.step({
                0: [0,0,0],
                1: [0,0,0],
                2: [0,0,0],
                3: [0,0,0]})
        
        states = [v for k,v in states.items()]
        rewards = [v for k,v in rewards.items()]
        done = [done['__all__'] for i in range(4)]
        return states, rewards, done, info
    
    def step_env(self, actions):
        """
        Realizes actions in environment and returns relevant attributes.

        Parameters:
            actions: Actions array to be realized in the environment.

        Returns:
            states: Array with next state information.
            rewards: Array with rewards information.
            dones: Array with boolean values with 'true' designating the
                episode has finished.
            env_info: BrainInfo object with current environment data.
        """
        # Construct the actions
        actions_to_take = {i:actions[i] if i < 2 else [0,0,0] for i in range(4)}
        #actions_to_take = {i: [0,0,0] for i in range(4)}
        # From environment information, extract states and rewards.
        obs, rewards, done, info = self.env.step(actions_to_take)

        states = [v for k,v in obs.items()]
        rewards = [v for k,v in rewards.items()]
        done = done['__all__']
        # Evaluate if episode has finished.
        return states, rewards, done, info

    def run_episode(self):
        """
        Runs a single episode in the training process for max_episode_length
        timesteps.

        Returns:
            scores: List of rewards gained at each timestep.
        """

        # Initialize list to hold reward values at each timestep.
        scores = []

        # Restart the environment and gather original states.
        states, rewards, done, _ = self.reset_env()
        episode_start = 0
        # Act and evaluate results and networks for each timestep.
        for t in range(self.max_episode_length):
            self.timestep += 1
            episode_start += 1
            # Sample actions for each agent while keeping track of states,
            # actions and log probabilities.
            processed_states, actions, log_probs = [], [], []
    
            for agent, state in zip(self.agents, states):
                processed_state = torch.from_numpy(state).float()
                action, log_prob = agent.get_actions(processed_state)
                processed_states.append(processed_state)
                log_probs.append(log_prob)
                actions.append(action)


            # Convert action tensors to integer values.
            raw_actions = np.array(
                [torch.clamp(a, -1, 1).numpy() for a in actions]
            )

            # Realize sampled actions in environment and evaluate new state.
            states, rewards, dones, info = self.step_env(raw_actions)
            times = [self.timestep==500] * 4
            
            # Add experience to the memories for each agent.
            for agent, state, action, log_prob, reward, time_ep in \
                    zip(self.agents, processed_states, actions, log_probs,
                        rewards, times):
                agent.add_memory(state, action, log_prob, reward, time_ep)

            # Initiate learning for agent if update frequency is observed.
            if self.timestep % self.update_frequency == 0:
                for agent in self.agents:
                    agent.update()

            # Append reward gained for each new action.
            scores.append(rewards)

            # End episode if desired score is achieved.
            
            if dones:
                #print(info)
                goal_check = False
                for i in rewards:
                    if i == -1.0:
                        goal_check = True
            
                if goal_check:
                    print("Goal Scored!, Reset Env")
                '''
                else:
                    print("Times up!, Reset Env")
                '''
                self.reset_env()
                # print(",")
                # print(t)
                # print(states)
                
                
            
        #print("Episode Ending")
        return scores

    def step(self):
        """
        Initiates run of an episode and logs the resulting total rewards and
        episode lengths.
        """

        # Run a single episode in environment.
        self.i_episode += 1
        scores = self.run_episode()

        # Sum the episode rewards for each agent to get the total rewards.
        score_by_agent = np.sum(scores, axis=0)

        # Store total rewards and episode lengths.
        self.score_history.append(score_by_agent)
        self.episode_length_history.append(len(scores))

    def save(self):
        """
        Saves actor_critic for both agents once successful score is achieved.
        """

        # Save actor_critic for each agent in specified save location.
        for agent_ix in range(len(self.agents)):
            agent = self.agents[agent_ix]
            filename = f'agent_{agent_ix}_episode_{self.i_episode}.pth'
            state_dict = agent.actor_critic.state_dict()
            torch.save(state_dict, os.path.join(self.save_dir, filename))

    def print_status(self):
        """Prints reward info and episode length stats at current episode."""

        # Calculate necessary statistics.
        mean_reward = np.mean(
            self.score_history[-self.score_window_size:],
            axis=0
        )
        agent_info = ''.join(f'Mean Reward Agent_{i}: {mean_reward[i]:.2f}, '
                             for i in range(len(self.agents)))
        max_mean = np.max(self.score_history[-self.score_window_size:],
                          axis=1).mean()
        mean_eps_len = np.mean(
            self.episode_length_history[-self.score_window_size:]
        ).item()

        # Print current status to terminal.
        print(
            f'\033[1mEpisode {self.i_episode} - '
            f'Mean Max Reward: {max_mean:.2f}\033[0m'
            f'\n\t{agent_info}\n\t'
            f'Mean Total Reward: {mean_reward.sum():.2f}, '
            f'Mean Episode Length {mean_eps_len:.1f}'
        )

    def plot(self):
        """
        Plots moving averages of maximum reward and rewards for each agent.
        """

        # Initialize DataFrame to be used for plot.
        columns = [f'Agent {i}' for i in range(len(self.agents))]
        df = pd.DataFrame(self.score_history, columns=columns)
        df['Max'] = df.max(axis=1)

        # Plot rewards per agent and cumulative moving averages.
        fig, ax = plt.subplots(figsize=(12, 9))
        ax.set_title(
            f'Learning Curve: Multi-Agent PPO',
            fontsize=28
        )
        ax.set_xlabel('Episode', fontsize=21)
        ax.set_ylabel('Score', fontsize=21)
        df.rolling(self.score_window_size).mean()\
            .plot(ax=ax, colormap='terrain')
        ax.grid(color='w', linewidth=0.2)
        ax.legend(fontsize=13)
        plt.tight_layout()

        # Save resulting plot.
        filename = f'scores_{self.i_episode}'
        fig.savefig(os.path.join(self.save_dir, filename))
        plt.show()
