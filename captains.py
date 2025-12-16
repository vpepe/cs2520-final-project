from random import random
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple

import numpy as np

from battleship.agents import ActionData
from battleship.agents import Agent
from battleship.agents import ANSWER_MATCH_PATTERN
from battleship.agents import DECISION_PATTERN
from battleship.agents import EIGCalculator
from battleship.agents import get_openai_client
from battleship.agents import MOVE_PATTERN
from battleship.agents import Question
from battleship.board import Board
from battleship.board import tile_to_coords
from battleship.fast_sampler import FastSampler
from battleship.game import Decision
from battleship.planner_captain import PlannedDecision
from battleship.planner_captain import PlannedMove
from battleship.planner_captain import PlannedQuestion
from battleship.planner_captain import StrategyPlanner
from battleship.prompting import DecisionPrompt
from battleship.prompting import MovePrompt
from battleship.prompting import QuestionPrompt
from battleship.stitch_derived_questions import build_stitch_question_bank
from battleship.strategies import DecisionStrategy
from battleship.strategies import MoveStrategy
from battleship.strategies import QuestionStrategy
from battleship.synthesis_engine import StrategyPopulation


class Captain(Agent):
    def __init__(
        self,
        decision_strategy=None,
        move_strategy=None,
        question_strategy=None,
        seed: int = None,
        llm=None,
        temperature=None,
        json_path=None,
    ):
        super().__init__(
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        self.temperature = temperature
        self.sampling_constraints = []

        # Optional strategies for modular approach
        self.decision_strategy = decision_strategy
        self.move_strategy = move_strategy
        self.question_strategy = question_strategy

    def decision(
        self,
        state: Board,
        history: List[Dict],
        questions_remaining: int,
        moves_remaining: int,
        ship_tracker: List[Tuple[int, Optional[str]]],
    ) -> Decision:
        decision, action_data = self.decision_strategy(
            state,
            history,
            questions_remaining,
            moves_remaining,
            ship_tracker,
        )

        # Save the action data
        self.save_action_data(action_data)

        return decision

    def move(
        self,
        state: Board,
        history: List[Dict],
        ship_tracker: List[Tuple[int, Optional[str]]],
        questions_remaining: int,
        moves_remaining: int,
        constraints: List,
    ):
        move, action_data = self.move_strategy(
            state,
            history,
            ship_tracker,
            questions_remaining,
            moves_remaining,
            constraints,
        )

        # Save the action data
        self.save_action_data(action_data)

        return move

    def question(
        self,
        state: Board,
        history: List[Dict],
        ship_tracker: List[Tuple[int, Optional[str]]],
        questions_remaining: int,
        moves_remaining: int,
        constraints: List,
    ):
        question, action_data = self.question_strategy(
            state,
            history,
            ship_tracker,
            questions_remaining,
            moves_remaining,
            constraints,
        )

        # Save the action data
        self.save_action_data(action_data)

        return question


# Example decision strategies
class AlwaysMoveDecisionStrategy(DecisionStrategy):
    def __call__(
        self, state, history, questions_remaining, moves_remaining, ship_tracker
    ):
        action_data = ActionData(
            action="decision",
            decision=Decision.MOVE,
            board_state=state.to_numpy(),
        )
        return Decision.MOVE, action_data


class ProbabilisticDecisionStrategy(DecisionStrategy):
    def __init__(self, q_prob=0.5):
        super().__init__()
        self.q_prob = q_prob

    def __call__(
        self, state, history, questions_remaining, moves_remaining, ship_tracker
    ):
        if random() < self.q_prob and questions_remaining > 0:
            decision = Decision.QUESTION
        else:
            decision = Decision.MOVE

        action_data = ActionData(
            action="decision",
            decision=decision,
            board_state=state.to_numpy(),
        )
        return decision, action_data


class LLMDecisionStrategy(DecisionStrategy):
    def __init__(
        self,
        llm,
        temperature=None,
        use_cot=False,
    ):
        super().__init__()
        self.llm = llm
        self.temperature = temperature
        self.use_cot = use_cot
        self.client = get_openai_client()

    def __call__(
        self,
        state,
        history,
        questions_remaining,
        moves_remaining,
        ship_tracker,
        n_attempts=3,
    ):
        if questions_remaining > 0:
            decision_prompt = DecisionPrompt(
                board=state,
                board_format="grid",
                history=history,
                use_cot=self.use_cot,
                questions_remaining=questions_remaining,
                moves_remaining=moves_remaining,
                ship_tracker=ship_tracker,
            )

            candidate_decision = None
            completion = None
            for _ in range(n_attempts):
                completion = self.client.chat.completions.create(
                    model=self.llm,
                    messages=decision_prompt.to_chat_format(),
                    temperature=self.temperature,
                )
                match = DECISION_PATTERN.search(completion.choices[0].message.content)

                if match is not None:
                    candidate_decision = match.group(1)
                    break

            decision = (
                Decision.MOVE if candidate_decision == "Move" else Decision.QUESTION
            )

        else:
            completion = None
            decision_prompt = None
            decision = Decision.MOVE

        # Create an ActionData object to store the interaction
        action_data = ActionData(
            action="decision",
            prompt=str(decision_prompt) if decision_prompt else None,
            completion=completion.model_dump() if completion else None,
            decision=decision,
            board_state=state.to_numpy(),
        )
        return decision, action_data


# Example move strategies
class RandomMoveStrategy(MoveStrategy):
    def __init__(self, rng):
        super().__init__()
        self.rng = rng

    def __call__(
        self,
        state,
        history,
        ship_tracker,
        questions_remaining,
        moves_remaining,
        constraints,
    ):
        hidden_tiles = np.argwhere(state.board == Board.hidden)
        if len(hidden_tiles) == 0:
            raise ValueError("No hidden tiles left.")
        coords = tuple(self.rng.choice(hidden_tiles))

        action_data = ActionData(
            action="move",
            move=coords,
            board_state=state.to_numpy(),
        )
        return coords, action_data


class MAPMoveStrategy(MoveStrategy):
    def __init__(self, rng, board_id, n_samples=1000):
        super().__init__()
        self.rng = rng
        self.board_id = board_id
        self.n_samples = n_samples

    def __call__(
        self,
        state,
        history,
        ship_tracker,
        questions_remaining,
        moves_remaining,
        constraints,
    ):
        sampler = FastSampler(
            board=state,
            ship_tracker=ship_tracker,
            seed=self.rng,
        )

        # Compute the posterior counts over board positions (handles constraints internally)
        posterior = sampler.compute_posterior(
            n_samples=self.n_samples,
            normalize=False,
            constraints=constraints,
        )

        # For tiles that have already been revealed, force their probability to -infinity
        posterior = posterior.astype(float)
        posterior[state.board != Board.hidden] = -np.inf

        # Select the tile with the maximum posterior probability (MAP estimate)
        flat_idx = int(np.argmax(posterior))

        # Map the flat index back to 2D coordinates
        move_coords = np.unravel_index(flat_idx, state.board.shape)
        move = tuple(move_coords)

        action_data = ActionData(
            action="move",
            move=move,
            map_prob=float(posterior.max()),
            board_state=state.to_numpy(),
        )
        return move, action_data


class LLMMoveStrategy(MoveStrategy):
    def __init__(
        self,
        llm,
        temperature=None,
        use_cot=False,
        n_attempts=3,
        rng=np.random.default_rng(),
    ):
        super().__init__()
        self.llm = llm
        self.temperature = temperature
        self.use_cot = use_cot
        self.n_attempts = n_attempts
        self.client = get_openai_client()
        self.rng = rng

    def __call__(
        self,
        state,
        history,
        ship_tracker,
        questions_remaining,
        moves_remaining,
        constraints,
    ):
        visible_tiles = list(zip(*np.where(state.board != Board.hidden)))

        move_prompt = MovePrompt(
            board=state,
            board_format="grid",
            history=history,
            use_cot=self.use_cot,
            questions_remaining=questions_remaining,
            moves_remaining=moves_remaining,
            ship_tracker=ship_tracker,
        )

        sampler = FastSampler(
            board=state,
            ship_tracker=ship_tracker,
            seed=self.rng,
        )

        posterior = sampler.compute_posterior(
            n_samples=1000,
            normalize=False,
        )

        completion = None
        for _ in range(self.n_attempts):
            completion = self.client.chat.completions.create(
                model=self.llm,
                messages=move_prompt.to_chat_format(),
                temperature=self.temperature,
            )

            candidate_move = MOVE_PATTERN(state.size).search(
                completion.choices[0].message.content
            )
            if candidate_move is not None:
                candidate_move = tile_to_coords(candidate_move.group(1))
                if candidate_move not in visible_tiles:
                    # Create an ActionData object to store the interaction
                    action_data = ActionData(
                        action="move",
                        prompt=str(move_prompt),
                        completion=completion.model_dump(),
                        move=candidate_move,
                        map_prob=float(posterior[candidate_move]),
                        board_state=state.to_numpy(),
                    )

                    return candidate_move, action_data

        # If no valid move found, return None with ActionData
        action_data = ActionData(
            action="move",
            prompt=str(move_prompt),
            completion=completion.model_dump() if completion else None,
            move=None,
            board_state=state.to_numpy(),
        )
        return None, action_data


# Example question strategies
class EIGQuestionStrategy(QuestionStrategy):
    def __init__(
        self,
        llm,
        spotter,
        rng,
        samples=100,
        k=3,
        use_cot=False,
        n_attempts=3,
    ):
        super().__init__()
        self.llm = llm
        self.spotter = spotter
        self.rng = rng
        self.samples = samples
        self.k = k
        self.use_cot = use_cot
        self.eig_calculator = EIGCalculator(seed=self.rng, samples=self.samples)
        self.n_attempts = n_attempts
        self.client = get_openai_client()

    def __call__(
        self,
        state,
        history,
        ship_tracker,
        questions_remaining,
        moves_remaining,
        constraints,
    ):
        best_question = None
        best_eig = -1
        best_action_data = None

        sampler = FastSampler(
            board=state,
            ship_lengths=Board.SHIP_LENGTHS,
            ship_labels=Board.SHIP_LABELS,
            seed=self.rng,
        )
        shared_weighted_boards = sampler.get_weighted_samples(
            n_samples=self.samples,
            constraints=constraints,
            epsilon=self.eig_calculator.epsilon,
        )

        candidate_question_list = []
        for _ in range(self.k):
            question_prompt = QuestionPrompt(
                board=state,
                board_format="grid",
                history=history,
                use_cot=self.use_cot,
                questions_remaining=questions_remaining,
                moves_remaining=moves_remaining,
                ship_tracker=ship_tracker,
            )

            candidate_question_text = None
            completion = None
            for _ in range(self.n_attempts):
                completion = self.client.chat.completions.create(
                    model=self.llm,
                    messages=question_prompt.to_chat_format(),
                    temperature=None,
                )
                match = ANSWER_MATCH_PATTERN.search(
                    completion.choices[0].message.content
                )
                if match:
                    candidate_question_text = match.group(1)
                    break

            if candidate_question_text is None:
                continue

            candidate_question = Question(text=candidate_question_text)

            # First translate the question
            code_question = self.spotter.translate(
                question=candidate_question,
                board=state,
                history=history,
            )

            # Then calculate EIG using shared weighted boards
            eig = self.eig_calculator(
                code_question=code_question,
                state=state,
                ship_tracker=ship_tracker,
                constraints=constraints,
                weighted_boards=shared_weighted_boards,
            )

            # Create an ActionData object to store the interaction
            action_data = ActionData(
                action="question",
                prompt=str(question_prompt),
                completion=completion.model_dump(),
                question=code_question,
                eig=eig,
                board_state=state.to_numpy(),
                eig_questions=None,
            )

            candidate_question_list.append(action_data.to_dict())

            # Update best question if this one has higher EIG
            if eig > best_eig:
                best_eig = eig
                best_question = candidate_question
                best_action_data = action_data

        best_action_data.eig_questions = candidate_question_list
        return best_question, best_action_data


class StitchQuestionStrategy(QuestionStrategy):
    """
    Question strategy using pre-defined Stitch abstractions.

    Evaluates EIG for 10 baked-in question functions derived from
    compression-optimal patterns discovered by Stitch. Selects the
    question with maximum EIG without requiring LLM calls.

    This enables direct comparison with EIGCaptain to test whether
    compression-optimal patterns translate to gameplay-optimal questions.
    """

    def __init__(
        self,
        rng,
        samples=100,
        eig_k=10,
    ):
        super().__init__()
        self.rng = rng
        self.samples = samples
        self.eig_calculator = EIGCalculator(seed=rng, samples=self.samples)
        self.question_bank = build_stitch_question_bank()
        self.eig_k = min(eig_k, len(self.question_bank))  # Can't evaluate more than we have

    def __call__(
        self,
        state,
        history,
        ship_tracker,
        questions_remaining,
        moves_remaining,
        constraints,
    ):
        """
        Evaluate EIG for all baked-in Stitch questions and return the best one.

        Strategy:
        1. Generate weighted board samples once (expensive operation)
        2. Evaluate EIG for each of the 10 Stitch questions using shared samples
        3. Return question with highest EIG

        This is significantly faster than EIGCaptain because:
        - No LLM API calls for question generation
        - No Spotter translation needed
        - Questions are pre-compiled and validated
        """
        best_question = None
        best_eig = -1
        best_action_data = None

        # Generate weighted board samples once and reuse for all EIG calculations
        sampler = FastSampler(
            board=state,
            ship_lengths=Board.SHIP_LENGTHS,
            ship_labels=Board.SHIP_LABELS,
            seed=self.rng,
        )
        shared_weighted_boards = sampler.get_weighted_samples(
            n_samples=self.samples,
            constraints=constraints,
            epsilon=self.eig_calculator.epsilon,
        )

        candidate_question_list = []

        # Evaluate EIG for each Stitch abstraction
        for idx, code_question in enumerate(self.question_bank[:self.eig_k]):
            # Calculate EIG using shared weighted boards
            eig = self.eig_calculator(
                code_question=code_question,
                state=state,
                ship_tracker=ship_tracker,
                constraints=constraints,
                weighted_boards=shared_weighted_boards,
            )

            # Create an ActionData object to store the interaction
            action_data = ActionData(
                action="question",
                prompt=f"[Stitch abstraction evaluation {idx+1}/{self.eig_k}]",
                completion=code_question.completion,
                question=code_question,
                eig=eig,
                board_state=state.to_numpy(),
                eig_questions=None,
            )

            candidate_question_list.append(action_data.to_dict())

            # Update best question if this one has higher EIG
            if eig > best_eig:
                best_eig = eig
                best_question = code_question.question
                best_action_data = action_data

        # Store all candidate EIGs in the best action data
        if best_action_data:
            best_action_data.eig_questions = candidate_question_list

        return best_question, best_action_data


class HybridStitchQuestionStrategy(QuestionStrategy):
    """
    Hybrid question strategy that combines LLM and Stitch abstractions.

    Process:
    1. Generate ONE LLM question (using LLMQuestionStrategy)
    2. Evaluate EIG of all Stitch abstraction questions
    3. Return whichever question (LLM or best Stitch) has the highest EIG

    This combines the creativity of LLM question generation with the reliability
    of compression-discovered patterns, letting the best question win.
    """

    def __init__(
        self,
        llm,
        spotter,
        rng,
        samples=100,
        use_cot=False,
        n_attempts=3,
        stitch_k=None,
    ):
        super().__init__()
        self.llm = llm
        self.spotter = spotter
        self.rng = rng
        self.samples = samples
        self.use_cot = use_cot
        self.eig_calculator = EIGCalculator(seed=self.rng, samples=self.samples)
        self.n_attempts = n_attempts
        self.client = get_openai_client()

        # Stitch question configuration
        self.question_bank = build_stitch_question_bank()
        self.stitch_k = stitch_k if stitch_k is not None else len(self.question_bank)
        self.stitch_k = min(self.stitch_k, len(self.question_bank))

    def __call__(
        self,
        state,
        history,
        ship_tracker,
        questions_remaining,
        moves_remaining,
        constraints,
    ):
        """
        1. Generate ONE LLM question
        2. Evaluate EIG of all Stitch questions
        3. Return whichever question (LLM or best Stitch) has the highest EIG
        """
        # Generate weighted board samples once and reuse
        sampler = FastSampler(
            board=state,
            ship_lengths=Board.SHIP_LENGTHS,
            ship_labels=Board.SHIP_LABELS,
            seed=self.rng,
        )
        shared_weighted_boards = sampler.get_weighted_samples(
            n_samples=self.samples,
            constraints=constraints,
            epsilon=self.eig_calculator.epsilon,
        )

        candidate_question_list = []

        # Phase 1: Generate ONE LLM question
        question_prompt = QuestionPrompt(
            board=state,
            board_format="grid",
            history=history,
            use_cot=self.use_cot,
            questions_remaining=questions_remaining,
            moves_remaining=moves_remaining,
            ship_tracker=ship_tracker,
        )

        llm_question_text = None
        llm_completion = None
        for _ in range(self.n_attempts):
            llm_completion = self.client.chat.completions.create(
                model=self.llm,
                messages=question_prompt.to_chat_format(),
                temperature=None,
            )
            match = ANSWER_MATCH_PATTERN.search(
                llm_completion.choices[0].message.content
            )
            if match:
                llm_question_text = match.group(1)
                break

        llm_question = None
        llm_eig = -1
        llm_action_data = None

        if llm_question_text is not None:
            llm_question = Question(text=llm_question_text)

            # Translate the LLM question
            llm_code_question = self.spotter.translate(
                question=llm_question,
                board=state,
                history=history,
            )

            # Calculate EIG for LLM question
            llm_eig = self.eig_calculator(
                code_question=llm_code_question,
                state=state,
                ship_tracker=ship_tracker,
                constraints=constraints,
                weighted_boards=shared_weighted_boards,
            )

            # Create ActionData for LLM question
            llm_action_data = ActionData(
                action="question",
                prompt=str(question_prompt),
                completion=llm_completion.model_dump(),
                question=llm_code_question,
                eig=llm_eig,
                board_state=state.to_numpy(),
                eig_questions=None,
            )

            candidate_question_list.append(llm_action_data.to_dict())

        # Phase 2: Evaluate ALL Stitch questions
        best_stitch_eig = -1
        best_stitch_question = None
        best_stitch_action_data = None

        for idx, code_question in enumerate(self.question_bank[:self.stitch_k]):
            eig = self.eig_calculator(
                code_question=code_question,
                state=state,
                ship_tracker=ship_tracker,
                constraints=constraints,
                weighted_boards=shared_weighted_boards,
            )

            # Create ActionData for Stitch question
            stitch_action_data = ActionData(
                action="question",
                prompt=f"[Stitch evaluation {idx+1}/{self.stitch_k}]",
                completion=code_question.completion,
                question=code_question,
                eig=eig,
                board_state=state.to_numpy(),
                eig_questions=None,
            )

            candidate_question_list.append(stitch_action_data.to_dict())

            # Track best Stitch question
            if eig > best_stitch_eig:
                best_stitch_eig = eig
                best_stitch_question = code_question.question
                best_stitch_action_data = stitch_action_data

        # Phase 3: Pick the winner (LLM or Stitch)
        used_stitch_question = False
        if best_stitch_eig > llm_eig:
            # Stitch won
            best_question = best_stitch_question
            best_action_data = best_stitch_action_data
            used_stitch_question = True
        else:
            # LLM won (or tied)
            best_question = llm_question
            best_action_data = llm_action_data

        # Store all candidates in best action data
        if best_action_data:
            best_action_data.eig_questions = candidate_question_list
            # Add metadata
            if isinstance(best_action_data.completion, dict):
                best_action_data.completion["used_stitch_question"] = used_stitch_question
                best_action_data.completion["llm_eig"] = llm_eig
                best_action_data.completion["best_stitch_eig"] = best_stitch_eig
            else:
                # Stitch question completion format
                best_action_data.completion = {
                    **best_action_data.completion,
                    "used_stitch_question": used_stitch_question,
                    "llm_eig": llm_eig,
                    "best_stitch_eig": best_stitch_eig,
                }

        return best_question, best_action_data


class LLMQuestionStrategy(QuestionStrategy):
    def __init__(
        self,
        llm,
        temperature=None,
        use_cot=False,
        spotter=None,
        rng=None,
        n_attempts=3,
    ):
        super().__init__()
        self.llm = llm
        self.temperature = temperature
        self.use_cot = use_cot
        self.n_attempts = n_attempts
        self.spotter = spotter
        self.rng = rng
        self.eig_calculator = EIGCalculator(seed=self.rng)
        self.client = get_openai_client()

    def __call__(
        self,
        state,
        history,
        ship_tracker,
        questions_remaining,
        moves_remaining,
        constraints,
    ):
        question_prompt = QuestionPrompt(
            board=state,
            board_format="grid",
            history=history,
            use_cot=self.use_cot,
            questions_remaining=questions_remaining,
            moves_remaining=moves_remaining,
            ship_tracker=ship_tracker,
        )

        completion = None
        for _ in range(self.n_attempts):
            completion = self.client.chat.completions.create(
                model=self.llm,
                messages=question_prompt.to_chat_format(),
                temperature=self.temperature,
            )

            candidate_question = ANSWER_MATCH_PATTERN.search(
                completion.choices[0].message.content
            )

            if candidate_question:
                candidate_question = candidate_question.group(1)
                question = Question(text=candidate_question)

                code_question = self.spotter.translate(
                    question=question,
                    board=state,
                    history=history,
                )

                eig = self.eig_calculator(
                    code_question=code_question,
                    state=state,
                    ship_tracker=ship_tracker,
                    constraints=constraints,
                )

                action_data = ActionData(
                    action="question",
                    prompt=str(question_prompt),
                    completion=completion.model_dump(),
                    question=code_question,
                    eig=eig,
                    board_state=state.to_numpy(),
                )

                return question, action_data

        # If no valid question found, return None with ActionData
        action_data = ActionData(
            action="question",
            prompt=str(question_prompt),
            completion=completion.model_dump() if completion else None,
            question=None,
            board_state=state.to_numpy(),
        )
        return None, action_data


class SynthesizedQuestionStrategy(QuestionStrategy):
    """
    Question strategy using compression-guided program synthesis.

    Generates novel question-asking strategies by evolving combinations
    of Stitch-discovered abstractions using genetic programming.

    Architecture:
        1. Population: 20 strategy genomes (weighted combinations of abstractions)
        2. Evaluation: Fitness = average EIG performance over games
        3. Evolution: Top 5 survivors + 15 offspring (crossover + mutation)
        4. Selection: Best strategy from population for each game

    This tests: "Can we discover NEW strategies by recombining
    compression-optimal patterns?"

    Usage modes:
        - evolve=True: Actively evolves population across games (SLOW but discovers)
        - evolve=False: Uses best fixed strategy from population (FAST)
    """

    def __init__(
        self,
        rng,
        samples=100,
        eig_k=10,
        population_size=20,
        evolve=True,
        evolution_frequency=5,  # Evolve every N games
        seed=None,
    ):
        """
        Initialize synthesized question strategy.

        Args:
            rng: Random number generator
            samples: Number of board samples for EIG calculation
            eig_k: Number of questions to evaluate per strategy
            population_size: Size of strategy population
            evolve: Whether to actively evolve strategies (True) or use best fixed (False)
            evolution_frequency: How often to trigger evolution (games per generation)
            seed: Random seed for population initialization
        """
        super().__init__()
        self.rng = rng
        self.samples = samples
        self.eig_calculator = EIGCalculator(seed=rng, samples=self.samples)
        self.eig_k = eig_k
        self.evolve = evolve
        self.evolution_frequency = evolution_frequency

        # Initialize strategy population
        self.population = StrategyPopulation(
            population_size=population_size,
            elite_size=max(1, population_size // 4),  # Keep top 25%
            mutation_rate=0.15,
            crossover_rate=0.7,
            seed=seed
        )

        # Track performance
        self.games_played = 0
        self.current_genome = self.population.get_best_genome()
        self.performance_log = []

    def __call__(
        self,
        state,
        history,
        ship_tracker,
        questions_remaining,
        moves_remaining,
        constraints,
    ):
        """
        Generate question using evolved strategy.

        Process:
            1. Select current strategy genome from population
            2. Sample k questions from strategy's weighted gene pool
            3. Evaluate EIG for each sampled question
            4. Return question with highest EIG
            5. Update strategy fitness based on performance
            6. Trigger evolution if needed
        """
        best_question = None
        best_eig = -1
        best_action_data = None

        # Generate weighted board samples once
        sampler = FastSampler(
            board=state,
            ship_lengths=Board.SHIP_LENGTHS,
            ship_labels=Board.SHIP_LABELS,
            seed=self.rng,
        )
        shared_weighted_boards = sampler.get_weighted_samples(
            n_samples=self.samples,
            constraints=constraints,
            epsilon=self.eig_calculator.epsilon,
        )

        candidate_question_list = []

        # Sample questions from current genome's gene pool
        candidate_questions = self.current_genome.sample_questions(
            k=self.eig_k,
            rng=self.rng
        )

        # Evaluate EIG for each candidate
        for idx, code_question in enumerate(candidate_questions):
            eig = self.eig_calculator(
                code_question=code_question,
                state=state,
                ship_tracker=ship_tracker,
                constraints=constraints,
                weighted_boards=shared_weighted_boards,
            )

            # Create ActionData
            action_data = ActionData(
                action="question",
                prompt=f"[Synthesized strategy evaluation {idx+1}/{len(candidate_questions)}]",
                completion={
                    **code_question.completion,
                    "genome_id": self.current_genome.genome_id,
                    "generation": self.current_genome.generation,
                    "genome_fitness": self.current_genome.fitness,
                },
                question=code_question,
                eig=eig,
                board_state=state.to_numpy(),
                eig_questions=None,
            )

            candidate_question_list.append(action_data.to_dict())

            # Track best
            if eig > best_eig:
                best_eig = eig
                best_question = code_question.question
                best_action_data = action_data

        # Store all candidates
        if best_action_data:
            best_action_data.eig_questions = candidate_question_list

            # Update genome fitness with this EIG score
            self.population.update_fitness(
                genome_id=self.current_genome.genome_id,
                fitness=best_eig
            )

            # Log performance
            self.performance_log.append({
                'genome_id': self.current_genome.genome_id,
                'generation': self.current_genome.generation,
                'eig': best_eig,
                'questions_asked': len(candidate_questions)
            })

        # Increment game counter and trigger evolution if needed
        self.games_played += 1
        if self.evolve and self.games_played % self.evolution_frequency == 0:
            self._trigger_evolution()

        return best_question, best_action_data

    def _trigger_evolution(self):
        """
        Evolve the population to next generation.

        Called every evolution_frequency games when evolve=True.
        Updates current_genome to best strategy from new generation.
        """
        self.population.evolve()

        # Select new current genome (best from population)
        self.current_genome = self.population.get_best_genome()

        # Log evolution event
        diversity = self.population.get_diversity_metric()
        print(f"[SynthesizedCaptain] Evolution triggered at game {self.games_played}")
        print(f"  Generation: {self.population.generation}")
        print(f"  Best fitness: {self.current_genome.fitness:.4f}")
        print(f"  Population diversity: {diversity:.4f}")
        print(f"  Current genome ID: {self.current_genome.genome_id}")

    def get_population_summary(self) -> dict:
        """
        Get summary statistics about the evolved population.

        Useful for post-hoc analysis of what strategies emerged.
        """
        return {
            'generation': self.population.generation,
            'games_played': self.games_played,
            'best_genome_id': self.current_genome.genome_id,
            'best_fitness': self.current_genome.fitness,
            'population_size': len(self.population.population),
            'diversity': self.population.get_diversity_metric(),
            'fitness_history': self.population.fitness_history,
            'performance_log': self.performance_log,
            'top_genes': self._get_top_genes()
        }

    def _get_top_genes(self, top_k: int = 5) -> list:
        """Get the top-weighted genes from current best strategy"""
        best_genome = self.population.get_best_genome()
        sorted_genes = sorted(
            best_genome.genes,
            key=lambda g: g.weight,
            reverse=True
        )
        return [
            {'name': gene.name, 'weight': gene.weight}
            for gene in sorted_genes[:top_k]
        ]


def create_captain(
    captain_type,
    seed,
    llm,
    board_id,
    map_samples=None,
    prob_q_prob=None,
    eig_samples=None,
    eig_k=None,
    gamma: float = 0.95,
    json_path=None,
):
    """
    Factory function to create Captain instances with properly configured strategies.
    """
    from battleship.spotters import create_spotter

    # Initialize spotter for EIG captains
    def _get_spotter():
        return create_spotter(
            spotter_type="CodeSpotterModel",
            board_id=board_id,
            board_experiment="collaborative",
            llm=llm,
            temperature=None,
            use_cot=True,
        )

    if captain_type == "RandomCaptain":
        return Captain(
            decision_strategy=AlwaysMoveDecisionStrategy(),
            move_strategy=RandomMoveStrategy(rng=np.random.default_rng(seed)),
            question_strategy=None,
            seed=seed,
            json_path=json_path,
        )

    elif captain_type == "MAPCaptain":
        return Captain(
            decision_strategy=AlwaysMoveDecisionStrategy(),
            move_strategy=MAPMoveStrategy(
                rng=np.random.default_rng(seed),
                board_id=board_id,
                n_samples=map_samples,
            ),
            question_strategy=None,
            seed=seed,
            json_path=json_path,
        )

    elif captain_type == "ProbabilisticCaptain":
        captain = Captain(
            decision_strategy=ProbabilisticDecisionStrategy(q_prob=prob_q_prob),
            move_strategy=LLMMoveStrategy(
                llm=llm,
                use_cot=False,
                rng=np.random.default_rng(seed),
            ),
            question_strategy=LLMQuestionStrategy(
                llm=llm,
                use_cot=False,
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "ProbabilisticCaptain_cot":
        captain = Captain(
            decision_strategy=ProbabilisticDecisionStrategy(q_prob=prob_q_prob),
            move_strategy=LLMMoveStrategy(
                llm=llm,
                use_cot=True,
                rng=np.random.default_rng(seed),
            ),
            question_strategy=LLMQuestionStrategy(
                llm=llm,
                use_cot=True,
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "LLMDecisionCaptain":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=False,
            ),
            move_strategy=LLMMoveStrategy(
                llm=llm,
                use_cot=False,
                rng=np.random.default_rng(seed),
            ),
            question_strategy=LLMQuestionStrategy(
                llm=llm,
                use_cot=False,
                spotter=_get_spotter(),
                rng=np.random.default_rng(seed),
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "LLMDecisionCaptain_cot":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=True,
            ),
            move_strategy=LLMMoveStrategy(
                llm=llm,
                use_cot=True,
                rng=np.random.default_rng(seed),
            ),
            question_strategy=LLMQuestionStrategy(
                llm=llm,
                use_cot=True,
                spotter=_get_spotter(),
                rng=np.random.default_rng(seed),
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "EIGCaptain":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=False,
            ),
            move_strategy=LLMMoveStrategy(
                llm=llm,
                use_cot=False,
                rng=np.random.default_rng(seed),
            ),
            question_strategy=EIGQuestionStrategy(
                llm=llm,
                spotter=_get_spotter(),
                rng=np.random.default_rng(seed),
                samples=eig_samples,
                k=eig_k,
                use_cot=False,
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "EIGCaptain_cot":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=True,
            ),
            move_strategy=LLMMoveStrategy(
                llm=llm,
                use_cot=True,
                rng=np.random.default_rng(seed),
            ),
            question_strategy=EIGQuestionStrategy(
                llm=llm,
                spotter=_get_spotter(),
                rng=np.random.default_rng(seed),
                samples=eig_samples,
                k=eig_k,
                use_cot=True,
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "StitchAbstractionCaptain":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=False,
            ),
            move_strategy=LLMMoveStrategy(
                llm=llm,
                use_cot=False,
                rng=np.random.default_rng(seed),
            ),
            question_strategy=StitchQuestionStrategy(
                rng=np.random.default_rng(seed),
                samples=eig_samples if eig_samples else 100,
                eig_k=eig_k if eig_k else len(build_stitch_question_bank()),
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "HybridStitchAbstractionCaptain":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=False,
            ),
            move_strategy=LLMMoveStrategy(
                llm=llm,
                use_cot=False,
                rng=np.random.default_rng(seed),
            ),
            question_strategy=HybridStitchQuestionStrategy(
                llm=llm,
                spotter=_get_spotter(),
                rng=np.random.default_rng(seed),
                samples=eig_samples if eig_samples else 100,
                use_cot=False,
                stitch_k=None,  # Evaluate all Stitch questions
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "SynthesizedCaptain":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=False,
            ),
            move_strategy=MAPMoveStrategy(
                rng=np.random.default_rng(seed),
                board_id=board_id,
                n_samples=eig_samples if eig_samples else 1000,
            ),
            question_strategy=SynthesizedQuestionStrategy(
                rng=np.random.default_rng(seed),
                samples=eig_samples if eig_samples else 100,
                eig_k=eig_k if eig_k else 10,
                population_size=20,
                evolve=True,  # Enable evolution
                evolution_frequency=5,  # Evolve every 5 games
                seed=seed,
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "SynthesizedCaptain_fixed":
        # Fixed strategy version (no evolution, faster)
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=False,
            ),
            move_strategy=MAPMoveStrategy(
                rng=np.random.default_rng(seed),
                board_id=board_id,
                n_samples=eig_samples if eig_samples else 1000,
            ),
            question_strategy=SynthesizedQuestionStrategy(
                rng=np.random.default_rng(seed),
                samples=eig_samples if eig_samples else 100,
                eig_k=eig_k if eig_k else 10,
                population_size=20,
                evolve=False,  # Disable evolution (use best fixed strategy)
                evolution_frequency=5,
                seed=seed,
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "MAPEIGCaptain":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=False,
            ),
            move_strategy=MAPMoveStrategy(
                rng=np.random.default_rng(seed),
                board_id=board_id,
                n_samples=eig_samples,
            ),
            question_strategy=EIGQuestionStrategy(
                llm=llm,
                spotter=_get_spotter(),
                rng=np.random.default_rng(seed),
                samples=eig_samples,
                k=eig_k,
                use_cot=False,
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type == "MAPEIGCaptain_cot":
        captain = Captain(
            decision_strategy=LLMDecisionStrategy(
                llm=llm,
                use_cot=True,
            ),
            move_strategy=MAPMoveStrategy(
                rng=np.random.default_rng(seed),
                board_id=board_id,
                n_samples=eig_samples,
            ),
            question_strategy=EIGQuestionStrategy(
                llm=llm,
                spotter=_get_spotter(),
                rng=np.random.default_rng(seed),
                samples=eig_samples,
                k=eig_k,
                use_cot=True,
            ),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        return captain

    elif captain_type in ("PlannerCaptain", "PlannerCaptain_cot"):
        use_cot = captain_type.endswith("_cot")

        # Build a shared planner and wire adapters
        planner = StrategyPlanner(
            llm=llm,
            spotter=_get_spotter(),
            rng=np.random.default_rng(seed),
            samples=eig_samples,
            k=eig_k,
            use_cot=use_cot,
            temperature=None,
            n_attempts=3,
        )

        captain = Captain(
            decision_strategy=PlannedDecision(planner, gamma=gamma),
            move_strategy=PlannedMove(planner),
            question_strategy=PlannedQuestion(planner),
            seed=seed,
            llm=llm,
            json_path=json_path,
        )
        # Connect planner to captain's live constraints list for per-stage planning
        planner.set_constraints_ref(captain.sampling_constraints)
        return captain

    else:
        raise ValueError(f"Unknown captain type: {captain_type}")
