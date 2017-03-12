# -*- coding: utf-8 -*-

import os
import sys
import subprocess as subp

import numpy as np

from sklearn.tree.tree import DecisionTreeClassifier
from sklearn.ensemble.weight_boosting import AdaBoostClassifier
from sklearn.ensemble.forest import RandomForestClassifier
from sklearn.ensemble.forest import ExtraTreesClassifier
from sklearn.svm.classes import LinearSVC
from sklearn.svm.classes import SVC
from sklearn.svm.classes import NuSVC
from sklearn.neighbors.classification import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB
from sklearn.naive_bayes import BernoulliNB


class Porter:
    __version__ = '0.4.0'

    def __init__(self, model, language='java', method='predict', **kwargs):
        """
        Port a trained model to the syntax of a chosen
        programming language.

        Parameters
        ----------
        model : sklearn.base.BaseEstimator
            A trained scikit-learn model.

        language : {'c', 'go', 'java', 'js', 'php', 'ruby'}, default 'java'
            The required target programming language.

        method : {'predict', 'predict_proba'}, default 'predict'
            The target prediction method.
        """
        self.model = model

        shared_properties = ('algorithm_name', 'algorithm_type')
        for prop in shared_properties:
            if hasattr(self, prop):
                setattr(self, prop, getattr(self, prop))

        # Import model class:
        package = '{algorithm_type}.' \
                  '{algorithm_name}'.format(**self.__dict__)
        level = -1 if sys.version_info < (3, 3) else 1
        try:
            clazz = __import__(package, globals(), locals(),
                               [self.algorithm_name], level)
            clazz = getattr(clazz, self.algorithm_name)
        except ImportError:
            error = "The given model '{algorithm_name}' " \
                    "isn't supported.".format(**self.__dict__)
            raise AttributeError(error)

        # Set target programming language:
        language = str(language).strip().lower()
        pwd = os.path.dirname(__file__)
        template_dir = os.path.join(pwd, self.algorithm_type,
                                    self.algorithm_name,
                                    'templates', language)
        has_template = os.path.isdir(template_dir)
        if not has_template:
            error = "The given target programming language" \
                    " '{}' isn't supported.".format(language)
            raise AttributeError(error)
        self.target_language = language

        # Set target prediction method:
        has_method = method in set(getattr(clazz, 'SUPPORTED_METHODS'))
        if not has_method:
            error = "The given model method" \
                    " '{}' isn't supported.".format(method)
            raise AttributeError(error)
        self.target_method = method

        # Create instance with all parameters:
        self.template = clazz(**self.__dict__)

        self.tested_env_dependencies = False

    @property
    def algorithm_name(self):
        """
        Get the algorithm class name.

        Returns
        -------
        name : string
            The class name of the used algorithm.
        """
        name = str(type(self.model).__name__)
        return name

    @property
    def algorithm_type(self):
        """
        Get the algorithm type.

        Returns
        -------
        type : {'classifier', 'regressor'}
            The type oof the used algorithm.
        """
        if isinstance(self.model, self.classifiers):
            return 'classifier'
        error = "The given model '{model}' isn't" \
                " supported.".format(**self.__dict__)
        raise ValueError(error)

    @property
    def classifiers(self):
        """
        Get a set of supported classifiers.

        Returns
        -------
        classifiers : {set}
            The supported classifiers.
        """

        # sklearn version < 0.18.0
        classifiers = (
            AdaBoostClassifier,
            BernoulliNB,
            DecisionTreeClassifier,
            ExtraTreesClassifier,
            GaussianNB,
            KNeighborsClassifier,
            LinearSVC,
            NuSVC,
            RandomForestClassifier,
            SVC,
        )

        # sklearn version >= 0.18.0
        from sklearn import __version__ as version
        version = version.split('.')
        version = [int(v) for v in version]
        major, minor = version[0], version[1]
        if major > 0 or (major == 0 and minor >= 18):
            from sklearn.neural_network.multilayer_perceptron \
                import MLPClassifier
            classifiers += (MLPClassifier, )

        return classifiers

    def export(self, class_name='Brain',
               method_name='predict',
               details=False, **kwargs):
        """
        Transpile a trained model to the syntax of a
        chosen programming language.

        Parameters
        ----------
        class_name : string, default 'Brain'
            The name for the ported class.

        method_name : string, default 'predict'
            The name for the ported method.

        details : bool, default False
            Return additional data for the compilation
            and execution.

        Returns
        -------
        model : {mix}
            The ported model as string or a dictionary
            with further information.
        """
        model = self.template.export(class_name=class_name,
                                      method_name=method_name)
        if not details:
            return model

        language = self.target_language
        filename = Porter.get_filename(class_name, language)
        comp_cmd, exec_cmd = Porter.get_commands(filename,
                                                 class_name,
                                                 language)
        output = {
            'model': str(model),
            'filename': filename,
            'class_name': class_name,
            'method_name': method_name,
            'cmd': {
                'compilation': comp_cmd,
                'execution': exec_cmd
            },
            'algorithm': {
                'type': self.algorithm_type,
                'name': self.algorithm_name
            }
        }
        return output

    def port(self, class_name='Brain',
             method_name='predict',
             details=False):
        """
        Transpile a trained model to the syntax of a
        chosen programming language.

        Parameters
        ----------
        class_name : string, default 'Brain'
            The name for the ported class.

        method_name : string, default 'predict'
            The name for the ported method.

        details : bool, default False
            Return additional data for the compilation
            and execution.

        Returns
        -------
        model : {mix}
            The ported model as string or a dictionary
            with further information.
        """
        loc = locals()
        loc.pop('self')
        return self.export(**loc)

    def predict(self, X, class_name='Brain', method_name='predict',
                tnp_dir='tmp', keep_tmp_dir=False):
        """
        Predict using the transpiled model.

        Parameters
        ----------
        X : {array-like}, shape (n_features) or (n_samples, n_features)
            The input data.

        class_name : string, default 'Brain'
            The name for the ported class.

        method_name : string, default 'predict'
            The name for the ported method.

        tnp_dir : string, default 'tmp'
            The path to the temporary directory for
            storing the transpiled (and compiled) model.

        keep_tmp_dir : bool, default False
            Whether to delete the temporary directory
            or not.

        Returns
        -------
            y : int or array-like, shape (n_samples,)
            The predicted class or classes.
        """

        # Dependencies:
        if not self.tested_env_dependencies:
            Porter.test_dependencies(self.target_language)

        # Support:
        if 'predict' not in set(self.template.SUPPORTED_METHODS):
            error = "The given model method" \
                    " '{}' isn't supported.".format('predict')
            raise AttributeError(error)

        # Cleanup:
        subp.call(['rm', '-rf', tnp_dir])
        subp.call(['mkdir', tnp_dir])

        # Transpiled model:
        details = self.export(class_name=class_name,
                              method_name=method_name,
                              details=True)
        filename = Porter.get_filename(class_name, self.target_language)
        target_file = os.path.join(tnp_dir, filename)
        with open(target_file, 'w') as f:
            f.write(details.get('model'))

        # Compilation command:
        comp_cmd = details.get('cmd').get('compilation')
        if comp_cmd is not None:
            comp_cmd = str(comp_cmd).split()
            subp.call(comp_cmd, cwd=tnp_dir)

        # Execution command:
        exec_cmd = details.get('cmd').get('execution')
        exec_cmd = str(exec_cmd).split()

        y = None

        # Single feature set:
        if exec_cmd is not None and len(X.shape) == 1:
            full_exec_cmd = exec_cmd + [str(f).strip() for f in X]
            pred = subp.check_output(full_exec_cmd, stderr=subp.STDOUT,
                                     cwd=tnp_dir)
            y = int(pred)

        # Multiple feature sets:
        if exec_cmd is not None and len(X.shape) > 1:
            y = np.empty(X.shape[0], dtype=int)
            for idx, x in enumerate(X):
                full_exec_cmd = exec_cmd + [str(f).strip() for f in x]
                pred = subp.check_output(full_exec_cmd, stderr=subp.STDOUT,
                                         cwd=tnp_dir)
                y[idx] = int(pred)

        # Cleanup:
        if not keep_tmp_dir:
            subp.call(['rm', '-rf', tnp_dir])

        return y

    @staticmethod
    def test_dependencies(language):
        """
        Check all target programming and operating
        system dependencies.

        Parameters
        ----------
        language : {'c', 'go', 'java', 'js', 'php', 'ruby'}
            The target programming language.
        """
        lang = str(language)

        # Dependencies:
        depends = {
            'c': ['gcc'],
            'java': ['java', 'javac'],
            'js': ['node'],
            # 'go': [],
            'php': ['php'],
            'ruby': ['ruby']
        }
        all_depends = depends.get(lang) + ['mkdir', 'rm']

        # Test:
        cmd = 'if hash {} 2/dev/null; then echo 1; else echo 0; fi'
        for exe in all_depends:
            cmd = cmd.format(exe)
            available = subp.check_output(cmd, shell=True,
                                          stderr=subp.STDOUT)
            available = available.strip() is '1'
            if not available:
                error = "The required application '{0}'" \
                        " isn't available.".format(exe)
                raise SystemError(error)

    @staticmethod
    def get_filename(class_name, language):
        """
        Generate the specific filename.

        Parameters
        ----------
        class_name : str
            The used class name.

        language : {'c', 'go', 'java', 'js', 'php', 'ruby'}
            The target programming language.

        Returns
        -------
            filename : str
            The generated filename.
        """
        name = str(class_name).lower()
        lang = str(language)

        # Name:
        if language == 'java':
            name = name.capitalize()

        # Suffix:
        suffix = {
            'c': 'c', 'java': 'java', 'js': 'js',
            'go': 'go', 'php': 'php', 'ruby': 'rb'
        }
        suffix = suffix.get(lang, lang)

        # Filename:
        return '{}.{}'.format(name, suffix)

    @staticmethod
    def get_commands(filename, class_name, language):
        """
        Generate the related compilation and
        execution commands.

        Parameters
        ----------
        filename : str
            The used filename.

        class_name : str
            The used class name.

        language : {'c', 'go', 'java', 'js', 'php', 'ruby'}
            The target programming language.

        Returns
        -------
            comp_cmd, exec_cmd : (str, str)
            The compilation and execution command.
        """
        cname = str(class_name).lower()
        fname = str(filename)
        lang = str(language)

        # Compilation variants:
        comp_vars = {
            # gcc brain.c -o brain
            'c': 'gcc {} -lm -o {}'.format(fname, cname),
            # javac Brain.java
            'java': 'javac {}'.format(fname)
        }
        comp_cmd = comp_vars.get(lang, None)

        # Execution variants:
        exec_vars = {
            # ./brain
            'c': os.path.join('.', cname),
            # java -classpath . Brain
            'java': 'java -classpath . {}'.format(cname.capitalize()),
            # node brain.js
            'js': 'node {}'.format(fname),
            # php -f brain.php
            'php': 'php -f {}'.format(fname),
            # ruby brain.rb
            'ruby': 'ruby {}'.format(fname)
        }
        exec_cmd = exec_vars.get(lang, None)

        return comp_cmd, exec_cmd