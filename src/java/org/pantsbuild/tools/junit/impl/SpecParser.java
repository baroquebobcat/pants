// Copyright 2016 Pants project contributors (see CONTRIBUTORS.md).
// Licensed under the Apache License, Version 2.0 (see LICENSE).

package org.pantsbuild.tools.junit.impl;

import com.google.common.base.Optional;
import java.lang.reflect.Method;
import java.security.AccessController;
import java.security.PrivilegedActionException;
import java.security.PrivilegedExceptionAction;
import java.util.Arrays;
import java.util.Collection;
import java.util.LinkedHashMap;
import java.util.concurrent.Callable;
import java.util.logging.Logger;

import com.google.common.base.Preconditions;
import com.google.common.collect.Iterables;

import org.pantsbuild.tools.junit.impl.security.JSecMgr;

/**
 * Takes strings passed to the command line representing packages or individual methods
 * and returns a parsed Spec.  Each Spec represents a single class, so individual methods
 * are added into each spec
 */
class SpecParser {
  private static final Logger logger = Logger.getLogger("junit-spec-parser");
  private final Iterable<String> testSpecStrings;
  private final LinkedHashMap<Class<?>, Spec> specs = new LinkedHashMap<>();

  /**
   * Parses the list of incoming test specs from the command line.
   * <p>
   * Expects a list of string specs which can be represented as one of:
   * <ul>
   *   <li>package.className</li>
   *   <li>package.className#methodName</li>
   * </ul>
   * Note that each class or method will only be executed once, no matter how many times it is
   * present in the list.
   * </p>
   * <p>
   * It is illegal to pass a spec with just the className if there are also individual methods
   * present in the list within the same class.
   * </p>
   */
  // TODO(zundel): This could easily be extended to allow a regular expression in the spec
  SpecParser(Iterable<String> testSpecStrings) {
    Preconditions.checkArgument(!Iterables.isEmpty(testSpecStrings));
    this.testSpecStrings = testSpecStrings;
  }

  /**
   * Parse the specs passed in to the constructor.
   *
   * @return List of parsed specs
   * @throws SpecException when there is a problem parsing specs
   */
  Collection<Spec> parse() throws SpecException {
    for (String specString : testSpecStrings) {
      if (specString.indexOf('#') >= 0) {
        addMethod(specString);
      } else {
        Optional<Spec> spec = getOrCreateSpec(specString, specString);
        if (spec.isPresent()) {
          Spec s = spec.get();
          if (specs.containsKey(s.getSpecClass()) && !s.getMethods().isEmpty()) {
            throw new SpecException(specString,
                "Request for entire class already requesting individual methods");
          }
        }
      }
    }
    return specs.values();
  }

  /**
   * Creates or returns an existing Spec that corresponds to the className parameter.
   *
   * @param className The class name already parsed out of specString
   * @param specString  A spec string described in {@link SpecParser}
   * @return a present Spec instance on success, absent if this spec string should be ignored
   * @throws SpecException if the method passed in is not an executable test method
   */
  private Optional<Spec> getOrCreateSpec(String className, String specString) throws SpecException {

    Class<?> clazz = loadOrThrow(className, specString);
    if (Util.isTestClass(clazz)) {
      if (!specs.containsKey(clazz)) {
        Spec newSpec = new Spec(clazz);
        specs.put(clazz, newSpec);
      }
      return Optional.of(specs.get(clazz));
    }
    return Optional.absent();
  }

  private Class<?> loadOrThrow(final String className, String specString) {
    try {

      // VV isn't right. This can't exec static client code.
      // ping sec mgr -- this execs static client code, so we want to be sure its covered
      return maybeWithSecurityManagerContext(className, new Callable<Class<?>>() {
        public Class<?> call() throws ClassNotFoundException {
          log("loading class for ... :" + className);

          Class<?> loadedClass = getClass().getClassLoader().loadClass(className);

          log("getClass().getClassLoader() " + getClass().getClassLoader());
          log("maybe try inspecting loaded class");
          log("name via class call: " + loadedClass.getCanonicalName());
          log("methods: " + Arrays.toString(loadedClass.getDeclaredMethods()));
          log("loading class successful for ... :" + className);

          return loadedClass;
        }
      });

    } catch (NoClassDefFoundError | ClassNotFoundException e) {
      throw new SpecException(specString,
          String.format("Class %s not found in classpath.", className), e);
    } catch (LinkageError e) {
      // Any of a number of runtime linking errors can occur when trying to load a class,
      // fail with the test spec so the class failing to link is known.
      throw new SpecException(specString,
          String.format("Error linking %s.", className), e);
      // See the comment below for justification.
    } catch (Exception e) {
      // The class may fail with some variant of RTE in its static initializers, trap these
      // and dump the bad spec in question to help narrow down issue.
      throw new SpecException(specString,
          String.format("Error initializing %s. %s blah %s",className, e, e.getCause()), e);
    }

  }

  private <T> T maybeWithSecurityManagerContext(final String className, final Callable<T> callable) throws Exception {
    SecurityManager securityManager = System.getSecurityManager();
    // skip if there is no security manager
    if (securityManager == null) {
      return callable.call();
    }
    final JSecMgr jsecMgr = (JSecMgr) securityManager;
    try {
      // doPrivileged here allows us to wrap all
      return AccessController.doPrivileged(
          new PrivilegedExceptionAction<T>() {
            @Override
            public T run() throws Exception {
              return jsecMgr.withSettings(
                  new JSecMgr.TestCaseSecurityContext(className, "static"),
                  callable);
            }
          },
          AccessController.getContext()
      );
    } catch (PrivilegedActionException e) {
      throw e.getException();
    }
  }

  private static void log(String msg) {
    logger.fine(msg);
  }

  /**
   * Handle a spec that looks like package.className#methodName
   */
  private void addMethod(String specString) throws SpecException {
    String[] results = specString.split("#");
    if (results.length != 2) {
      throw new SpecException(specString, "Expected only one # in spec");
    }
    String className = results[0];
    String methodName = results[1];

    Optional<Spec> spec = getOrCreateSpec(className, specString);
    if (spec.isPresent()) {
      Spec s = spec.get();
      for (Method clazzMethod : s.getSpecClass().getMethods()) {
        if (clazzMethod.getName().equals(methodName)) {
          Spec specWithMethod = s.withMethod(methodName);
          specs.put(s.getSpecClass(), specWithMethod);
          return;
        }
      }
      // TODO(John Sirois): Introduce an Either type to make this function total.
      throw new SpecException(specString,
          String.format("Method %s not found in class %s", methodName, className));
    }
  }
}
